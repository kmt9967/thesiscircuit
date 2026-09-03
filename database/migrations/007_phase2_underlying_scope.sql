-- Expand only the immutable session scope validator; no table or historical row changes.
begin;
create or replace function public.phase2_create_execution_session(document jsonb) returns jsonb
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
  or document->'allowed_underlyings' not in
      ('["SPY"]'::jsonb,'["QQQ"]'::jsonb,'["SPY","QQQ"]'::jsonb,'["QQQ","SPY"]'::jsonb)
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
revoke all on function public.phase2_create_execution_session(jsonb) from public,anon,authenticated;
grant execute on function public.phase2_create_execution_session(jsonb) to service_role;
commit;
