-- Additive finite-session authorization. Existing schema/functions/history are untouched.
begin;
create table public.phase2_execution_sessions (
 id uuid primary key, document jsonb not null,
 status text not null default 'DRAFT' check(status in ('DRAFT','ACTIVE','EXPIRED','KILLED','COMPLETED')),
 opening_consumed integer not null default 0 check(opening_consumed>=0),
 closing_consumed integer not null default 0 check(closing_consumed>=0),
 orders_consumed integer not null default 0 check(orders_consumed=opening_consumed+closing_consumed),
 new_risk_consumed numeric not null default 0 check(new_risk_consumed>=0),
 reservations jsonb not null default '{}', broker_failures jsonb not null default '[]',
 cycles jsonb not null default '{}', next_cycle_at timestamptz,
 kill_reason text, completed_at timestamptz, events jsonb not null default '[]',
 check(document->>'paper_mode'='true'),
 check(document->>'classification' in ('PAPER','SYNTHETIC'))
);
create unique index phase2_one_active_paper_session on public.phase2_execution_sessions
 ((document->>'classification')) where status='ACTIVE' and document->>'classification'='PAPER';
create index phase2_session_reservations on public.phase2_execution_sessions using gin(reservations);
alter table public.phase2_execution_sessions enable row level security;
revoke all on public.phase2_execution_sessions from public,anon,authenticated,service_role;
grant select on public.phase2_execution_sessions to service_role;

create function public.phase2_create_execution_session(document jsonb) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare s public.phase2_execution_sessions; duration interval;
begin
 perform pg_advisory_xact_lock(726026);
 if document is null or not (document ?& array['id','created_at','starts_at','expires_at','paper_mode',
  'classification','approval_equity','max_opening_orders','max_closing_orders','max_total_orders',
  'max_simultaneous_positions','max_new_risk','max_aggregate_premium_risk','allowed_underlyings',
  'allowed_strategy_types','entry_permission','exit_permission','manage_existing_position','allow_position_exit',
  'existing_position_symbols','daily_drawdown_fraction','cadence_seconds','max_cycles','max_broker_failures'])
  or exists(select 1 from jsonb_each(document) d where d.value='null'::jsonb)
  or document->>'paper_mode' is distinct from 'true'
  or document->>'classification' not in ('PAPER','SYNTHETIC') then raise exception 'Invalid session document'; end if;
 if exists(select 1 from unnest(array['entry_permission','exit_permission','manage_existing_position',
     'allow_position_exit']) k where jsonb_typeof(document->k)<>'boolean')
  or jsonb_typeof(document->'existing_position_symbols')<>'array'
  or jsonb_array_length(document->'existing_position_symbols')>3
  or (document->>'approval_equity')::numeric in ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)
  or (document->>'max_aggregate_premium_risk')::numeric in ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)
 then raise exception 'Invalid session field types'; end if;
 duration:=(document->>'expires_at')::timestamptz-(document->>'created_at')::timestamptz;
 if duration not between interval '1 second' and interval '1 hour'
  or (document->>'starts_at')::timestamptz<(document->>'created_at')::timestamptz
  or (document->>'starts_at')::timestamptz>=(document->>'expires_at')::timestamptz
  or (document->>'max_opening_orders')::int not between 0 and 1
  or (document->>'max_closing_orders')::int not between 0 and 3
  or (document->>'max_total_orders')::int not between 0 and 4
  or (document->>'max_total_orders')::int>(document->>'max_opening_orders')::int+(document->>'max_closing_orders')::int
  or (document->>'max_simultaneous_positions')::int not between 1 and 3
  or (document->>'approval_equity')::numeric<=0
  or (document->>'max_new_risk')::numeric not between 0 and least(500,(document->>'approval_equity')::numeric*0.005)
  or (document->>'max_aggregate_premium_risk')::numeric not between 0.01 and (document->>'approval_equity')::numeric*0.02
  or (document->>'daily_drawdown_fraction')::numeric not between 0.000001 and 0.01
  or (document->>'cadence_seconds')::int not between 60 and 3600
  or (document->>'max_cycles')::int not between 1 and 3
  or (document->>'max_broker_failures')::int not between 1 and 2
  or document->'allowed_underlyings' <> '["SPY"]'::jsonb
  or not (document->'allowed_strategy_types' <@ '["LONG_CALL","LONG_PUT"]'::jsonb)
  or jsonb_array_length(document->'allowed_strategy_types') not between 1 and 2
  or document->>'exit_permission' is distinct from document->>'allow_position_exit'
  or ((document->>'max_closing_orders')::int>0 and document->>'exit_permission'<>'true') then
  raise exception 'Unbounded or inconsistent session'; end if;
 select * into s from public.phase2_execution_sessions where id=(phase2_create_execution_session.document->>'id')::uuid;
 if found then
  if s.document is distinct from document then raise exception 'Immutable session conflict'; end if;
  return to_jsonb(s);
 end if;
 insert into public.phase2_execution_sessions(id,document,events)
 values((phase2_create_execution_session.document->>'id')::uuid,phase2_create_execution_session.document,
  jsonb_build_array(jsonb_build_object('kind','CREATED_DRAFT','at',clock_timestamp(),
   'classification',phase2_create_execution_session.document->>'classification'))) returning * into s;
 return to_jsonb(s);
end $$;

create function public.phase2_session_control(session_id uuid, action text,
 reason_code text default null, cycle_key uuid default null) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare s public.phase2_execution_sessions; stamp timestamptz;
begin
 perform pg_advisory_xact_lock(726026);
 select * into s from public.phase2_execution_sessions where id=session_id for update;
 if not found then raise exception 'Session missing'; end if;
 stamp:=clock_timestamp();
 if s.status in ('DRAFT','ACTIVE') and (s.document->>'expires_at')::timestamptz<=stamp then
  update public.phase2_execution_sessions set status='EXPIRED',completed_at=stamp,kill_reason='SESSION_EXPIRED',
   events=events||jsonb_build_array(jsonb_build_object('kind','EXPIRED','at',stamp))
   where id=session_id returning * into s;
 end if;
 if action='INSPECT' or s.status in ('EXPIRED','KILLED','COMPLETED') then return to_jsonb(s); end if;
 if action='ACTIVATE' then
  if s.status='ACTIVE' then return to_jsonb(s); end if;
  if stamp<(s.document->>'starts_at')::timestamptz then raise exception 'Session not started'; end if;
  -- Expired authorizations cannot block a newly approved finite session.
  update public.phase2_execution_sessions set status='EXPIRED',completed_at=stamp,kill_reason='SESSION_EXPIRED',
   events=events||jsonb_build_array(jsonb_build_object('kind','EXPIRED','at',stamp))
   where status='ACTIVE' and (document->>'expires_at')::timestamptz<=stamp;
  update public.phase2_execution_sessions set status='ACTIVE',
   events=events||jsonb_build_array(jsonb_build_object('kind','ACTIVATED','at',stamp))
   where id=session_id returning * into s;
 elsif action='KILL' then
  if reason_code is null or reason_code not in ('DRAWDOWN','AGGREGATE_RISK','MAX_POSITIONS','STALE_DATA',
   'LIVE_CONFIGURATION','CONFIG_MISMATCH','COMPETITION_CLOSED','BROKER_FAILURES','UNKNOWN_ORDER',
   'DATABASE_FAILURE','MANUAL_KILL','AUTHORIZATION_DENIED','SESSION_SCOPE','MARKET_CLOSED') then
    raise exception 'Invalid sanitized kill reason'; end if;
  update public.phase2_execution_sessions set status='KILLED',kill_reason=reason_code,completed_at=stamp,
   events=events||jsonb_build_array(jsonb_build_object('kind','KILLED','reason',reason_code,'at',stamp))
   where id=session_id returning * into s;
 elsif action='FINISH' then
  update public.phase2_execution_sessions set status='COMPLETED',completed_at=stamp,
   events=events||jsonb_build_array(jsonb_build_object('kind','COMPLETED','at',stamp))
   where id=session_id returning * into s;
 elsif action='CYCLE_START' then
  if s.status<>'ACTIVE' or cycle_key is null then raise exception 'Active bounded cycle required'; end if;
  if s.cycles ? cycle_key::text then return to_jsonb(s); end if;
  if (select count(*) from jsonb_object_keys(s.cycles)) >= (s.document->>'max_cycles')::int
   or s.next_cycle_at>stamp then raise exception 'Cycle budget or cadence exhausted'; end if;
  update public.phase2_execution_sessions set cycles=jsonb_set(cycles,array[cycle_key::text],
    jsonb_build_object('status','STARTED','at',stamp)),
   next_cycle_at=stamp+make_interval(secs=>(s.document->>'cadence_seconds')::int),
   events=events||jsonb_build_array(jsonb_build_object('kind','CYCLE_START','cycle_id',cycle_key,'at',stamp))
   where id=session_id returning * into s;
 elsif action='CYCLE_END' then
  if cycle_key is null or not s.cycles ? cycle_key::text or reason_code not in ('NO_TRADE','CANDIDATE','MONITOR_ONLY','ORDER_RECONCILED') then
   raise exception 'Invalid cycle completion'; end if;
  update public.phase2_execution_sessions set cycles=jsonb_set(cycles,array[cycle_key::text],
    jsonb_build_object('status',reason_code,'at',stamp)),
   events=events||jsonb_build_array(jsonb_build_object('kind','CYCLE_END','cycle_id',cycle_key,'reason',reason_code,'at',stamp))
   where id=session_id returning * into s;
 else raise exception 'Invalid session control action'; end if;
 return to_jsonb(s);
end $$;

create function public.phase2_session_order_gate(session_id uuid, intent_id uuid, worker uuid,
 action text, preflight jsonb default null) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare s public.phase2_execution_sessions; r public.phase2_order_intents; stamp timestamptz;
 reservation jsonb; risk numeric; direction text; strategy text; result jsonb;
begin
 -- Global order lock first: same ordering as Phase 2.5, then session lock.
 perform pg_advisory_xact_lock(725025);
 perform pg_advisory_xact_lock(726026);
 select * into s from public.phase2_execution_sessions where id=session_id for update;
 if not found then raise exception 'Session missing'; end if;
 select * into r from public.phase2_order_intents where id=intent_id for update;
 if not found then raise exception 'Intent missing'; end if;
 stamp:=clock_timestamp();
 if s.document->>'classification' is distinct from r.document->>'classification' then
  raise exception 'Session classification mismatch'; end if;
 reservation:=s.reservations->intent_id::text;
 if action='RESULT' then
  if reservation is null then raise exception 'Budget reservation missing'; end if;
  if r.status='UNKNOWN' then
   perform public.phase2_session_control(session_id,'KILL','UNKNOWN_ORDER');
  elsif r.status='REJECTED' and r.attempt_count>0 and not s.broker_failures ? intent_id::text then
   update public.phase2_execution_sessions set broker_failures=broker_failures||to_jsonb(intent_id::text)
    where id=session_id returning * into s;
   if jsonb_array_length(s.broker_failures)>=(s.document->>'max_broker_failures')::int then
    perform public.phase2_session_control(session_id,'KILL','BROKER_FAILURES'); end if;
  end if;
  return jsonb_build_object('allowed',true,'status',r.status);
 end if;
 if s.status in ('DRAFT','ACTIVE') and (s.document->>'expires_at')::timestamptz<=stamp then
  perform public.phase2_session_control(session_id,'INSPECT');
  return jsonb_build_object('allowed',false,'reason','SESSION_EXPIRED');
 end if;
 if s.status<>'ACTIVE' or stamp<(s.document->>'starts_at')::timestamptz then
  return jsonb_build_object('allowed',false,'reason','SESSION_INACTIVE'); end if;
 if not s.cycles ? (r.document->>'cycle_id') then
  return jsonb_build_object('allowed',false,'reason','SESSION_CYCLE_REQUIRED'); end if;
 if r.owner_id is distinct from worker or worker is null or r.claim_expires_at<=stamp then
  raise exception 'Exclusive order claim required'; end if;
 if exists(select 1 from public.phase2_order_intents o where o.status='UNKNOWN'
  and o.document->>'classification'=s.document->>'classification'
  and (s.document->>'classification'='PAPER' or s.reservations ? o.id::text)) then
  perform public.phase2_session_control(session_id,'KILL','UNKNOWN_ORDER');
  return jsonb_build_object('allowed',false,'reason','UNKNOWN_ORDER'); end if;
 direction:=r.document->>'action'; risk:=(r.document->>'expected_max_loss')::numeric;
 strategy:=case when r.document->'proposal'->'contract'->>'kind'='call' then 'LONG_CALL' else 'LONG_PUT' end;
 if not (s.document->'allowed_underlyings' ? (r.document->>'underlying'))
  or not (s.document->'allowed_strategy_types' ? strategy)
  or (direction='OPEN' and s.document->>'entry_permission'<>'true')
  or (direction='CLOSE' and (s.document->>'exit_permission'<>'true' or s.document->>'allow_position_exit'<>'true'))
  or (direction='CLOSE' and s.document->'existing_position_symbols' ? (r.document->'contracts'->>0)
      and s.document->>'manage_existing_position'<>'true') then
  return jsonb_build_object('allowed',false,'reason','SESSION_SCOPE'); end if;
 if action='RESERVE' then
  if reservation is not null then return jsonb_build_object('allowed',true,'replayed',true); end if;
  if r.status<>'CLAIMED' or r.attempt_count<>0 then raise exception 'Only never-sent claimed intents may reserve'; end if;
  if exists(select 1 from public.phase2_execution_sessions x where x.id<>session_id and x.reservations ? intent_id::text) then
   return jsonb_build_object('allowed',false,'reason','INTENT_ALREADY_BUDGETED'); end if;
  if s.orders_consumed>=(s.document->>'max_total_orders')::int
   or (direction='OPEN' and s.opening_consumed>=(s.document->>'max_opening_orders')::int)
   or (direction='CLOSE' and s.closing_consumed>=(s.document->>'max_closing_orders')::int)
   or s.new_risk_consumed+risk>(s.document->>'max_new_risk')::numeric then
   return jsonb_build_object('allowed',false,'reason','ORDER_BUDGET_EXHAUSTED'); end if;
  update public.phase2_execution_sessions set orders_consumed=orders_consumed+1,
   opening_consumed=opening_consumed+case when direction='OPEN' then 1 else 0 end,
   closing_consumed=closing_consumed+case when direction='CLOSE' then 1 else 0 end,
   new_risk_consumed=new_risk_consumed+risk,
   reservations=jsonb_set(reservations,array[intent_id::text],jsonb_build_object('action',direction,
     'risk',risk,'at',stamp,'cycle_id',r.document->>'cycle_id')),
   events=events||jsonb_build_array(jsonb_build_object('kind','BUDGET_CONSUMED','intent_id',intent_id,'at',stamp))
   where id=session_id;
  return jsonb_build_object('allowed',true,'replayed',false);
 elsif action='SUBMIT' then
  if reservation is null then raise exception 'Budget reservation missing'; end if;
  if (s.document->>'expires_at')::timestamptz<stamp+interval '15 seconds' then
   return jsonb_build_object('allowed',false,'reason','SESSION_NEAR_EXPIRY'); end if;
  -- Same transaction: session active, budget irrevocably spent, cycle fenced, one attempt only.
  result:=public.phase2_advance_order_intent(intent_id,worker,'SUBMITTING',null,null,preflight);
  update public.phase2_execution_sessions set events=events||jsonb_build_array(
   jsonb_build_object('kind','DISPATCH_FENCED','intent_id',intent_id,'at',stamp)) where id=session_id;
  return jsonb_build_object('allowed',true,'intent',result);
 else raise exception 'Invalid order-budget action'; end if;
end $$;
revoke all on function public.phase2_create_execution_session(jsonb) from public,anon,authenticated;
revoke all on function public.phase2_session_control(uuid,text,text,uuid) from public,anon,authenticated;
revoke all on function public.phase2_session_order_gate(uuid,uuid,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.phase2_create_execution_session(jsonb) to service_role;
grant execute on function public.phase2_session_control(uuid,text,text,uuid) to service_role;
grant execute on function public.phase2_session_order_gate(uuid,uuid,uuid,text,jsonb) to service_role;
commit;
