-- Additive Phase 2.5. No historical table, function or audit row is modified.
begin;
create table public.phase2_order_intents (
  id uuid primary key,
  document jsonb not null,
  status text not null default 'PENDING' check(status in
    ('PENDING','CLAIMED','SUBMITTING','SUBMITTED','RECONCILING','FILLED','CANCELED','REJECTED','EXPIRED','UNKNOWN')),
  owner_id uuid, claim_expires_at timestamptz, claimed_at timestamptz,
  submitted_at timestamptz, reconciled_at timestamptz,
  attempt_count integer not null default 0 check(attempt_count between 0 and 1),
  alpaca_order_id uuid unique, last_error text, broker_state jsonb,
  events jsonb not null default '[]',
  check(document->>'paper_mode' = 'true'),
  check(document->>'classification' in ('PAPER','SYNTHETIC')),
  check((document->>'id')::uuid = id)
);
create unique index phase2_intent_client_id on public.phase2_order_intents ((document->>'client_order_id'));
-- A proposal cannot be replayed in a different cycle under a fresh intent ID.
create unique index phase2_intent_logical_action on public.phase2_order_intents
  ((document->>'classification'),(document->>'proposal_id'),(document->>'action'));
-- UNKNOWN remains an account-wide barrier until real broker state is reconciled.
create unique index phase2_one_active_paper_intent on public.phase2_order_intents
  ((document->>'classification')) where document->>'classification'='PAPER'
    and status in ('CLAIMED','SUBMITTING','SUBMITTED','RECONCILING','UNKNOWN');
alter table public.phase2_order_intents enable row level security;
revoke all on public.phase2_order_intents from public,anon,authenticated,service_role;
grant select on public.phase2_order_intents to service_role;

create function public.phase2_create_order_intent(document jsonb, cycle_owner uuid)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.phase2_order_intents; l public.phase2_cycle_lease; stamp timestamptz;
begin
  perform pg_advisory_xact_lock(725025);
  stamp:=clock_timestamp();
  if document is null or cycle_owner is null or document->>'paper_mode' is distinct from 'true'
    or not (document ?& array['id','cycle_id','proposal_id','risk_decision_id','action','underlying',
      'contracts','side','quantity','order_type','limit_price','client_order_id','expected_max_loss',
      'created_at','risk_approved_at','classification','proposal','risk','paper_mode','time_in_force'])
    or exists(select 1 from jsonb_each(document) d where d.value='null'::jsonb)
    or coalesce(document->>'classification','') not in ('PAPER','SYNTHETIC')
    or coalesce(document->>'action','') not in ('OPEN','CLOSE')
    or document->>'order_type' is distinct from 'limit' or document->>'time_in_force' is distinct from 'day'
    or document->'risk'->>'decision' is distinct from 'APPROVED'
    or coalesce(jsonb_array_length(document->'risk'->'checks'),0)=0
    or exists(select 1 from jsonb_array_elements(document->'risk'->'checks') g where g->>'passed' is distinct from 'true')
    or document->>'client_order_id' is distinct from 'tc-p2-'||(document->>'id')
    or (document->>'quantity')::integer not between 1 and 3
    or (document->>'limit_price')::numeric <= 0
    or (document->>'expected_max_loss')::numeric not between 0 and 500
    or (document->>'cycle_id')::uuid is null or (document->>'risk_decision_id')::uuid is null
    or (document->>'proposal_id')::uuid is distinct from (document->'proposal'->>'id')::uuid
    or (document->>'proposal_id')::uuid is distinct from (document->'risk'->>'proposal_id')::uuid
    or jsonb_array_length(document->'contracts') <> 1 then
    raise exception 'Invalid immutable paper intent'; end if;
  select * into r from public.phase2_order_intents where id=(phase2_create_order_intent.document->>'id')::uuid;
  if found then
    if r.document is distinct from document then raise exception 'Immutable intent conflict'; end if;
    return to_jsonb(r);
  end if;
  if (document->>'created_at')::timestamptz not between stamp-interval '120 seconds' and stamp
    or (document->>'risk_approved_at')::timestamptz not between stamp-interval '120 seconds' and stamp then
    raise exception 'Stale intent or approval'; end if;
  if document->>'classification'='PAPER' then
    select * into l from public.phase2_cycle_lease where singleton for update;
    if l.owner_id is distinct from cycle_owner or l.cycle_id is distinct from (document->>'cycle_id')::uuid
       or l.expires_at <= clock_timestamp() then raise exception 'Cycle lease lost'; end if;
  end if;
  insert into public.phase2_order_intents(id,document,events)
    values((phase2_create_order_intent.document->>'id')::uuid,phase2_create_order_intent.document,
    jsonb_build_array(jsonb_build_object('kind','PENDING','at',stamp,
      'classification',phase2_create_order_intent.document->>'classification')))
    returning * into r;
  return to_jsonb(r);
end $$;

create function public.phase2_claim_order_intent(intent_id uuid, worker uuid)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.phase2_order_intents; l public.phase2_cycle_lease; stamp timestamptz;
begin
  perform pg_advisory_xact_lock(725025);
  select * into l from public.phase2_cycle_lease where singleton for update;
  select * into r from public.phase2_order_intents where id=intent_id for update;
  stamp:=clock_timestamp();
  if not found or worker is null then raise exception 'Intent or worker missing'; end if;
  if r.status in ('FILLED','CANCELED','REJECTED','EXPIRED') then return to_jsonb(r); end if;
  if r.owner_id is not null and r.claim_expires_at>stamp then
    if r.owner_id=worker then return to_jsonb(r); end if;
    raise exception 'Intent already claimed';
  end if;
  if r.status in ('PENDING','CLAIMED') and r.document->>'classification'='PAPER' then
    if l.cycle_id=(r.document->>'cycle_id')::uuid and l.expires_at>stamp and l.owner_id is distinct from worker then
      raise exception 'Cycle belongs to another worker'; end if;
    if l.owner_id is distinct from worker or l.cycle_id is distinct from (r.document->>'cycle_id')::uuid
      or l.expires_at<=stamp then
      -- A never-sent orphan must not permanently hold the account-wide barrier.
      -- An expired owner can no longer cross SUBMITTING; no broker cancellation occurs.
      update public.phase2_order_intents set status='EXPIRED',owner_id=null,claim_expires_at=null,
        last_error='CYCLE_LEASE_LOST',events=r.events||jsonb_build_array(jsonb_build_object(
          'kind','EXPIRED','at',stamp,'reason','cycle_lease_lost_before_send'))
        where id=intent_id returning * into r;
      return to_jsonb(r);
    end if;
  end if;
  update public.phase2_order_intents set owner_id=worker,
    claim_expires_at=stamp+interval '30 seconds', claimed_at=stamp,
    status=case when r.status='PENDING' then 'CLAIMED' else r.status end,
    events=r.events||jsonb_build_array(jsonb_build_object('kind','CLAIM','at',stamp,
      'recovery',r.owner_id is not null,'classification',r.document->>'classification'))
    where id=intent_id returning * into r;
  return to_jsonb(r);
end $$;

create function public.phase2_advance_order_intent(intent_id uuid, worker uuid, target text,
  broker jsonb default null, error_code text default null, preflight jsonb default null)
returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare r public.phase2_order_intents; l public.phase2_cycle_lease; stamp timestamptz;
begin
  perform pg_advisory_xact_lock(725025);
  select * into l from public.phase2_cycle_lease where singleton for update;
  select * into r from public.phase2_order_intents where id=intent_id for update;
  stamp:=clock_timestamp();
  if not found or worker is null or r.owner_id is distinct from worker or r.claim_expires_at<=stamp then
    raise exception 'Order claim lost'; end if;
  if r.status in ('FILLED','CANCELED','REJECTED','EXPIRED') then raise exception 'Terminal replay denied'; end if;
  if error_code is not null and error_code not in ('RECONCILIATION_REQUIRED','LOOKUP_UNCERTAIN',
    'STALE_INTENT_OR_RISK','TERMS_CHANGED_OR_DUPLICATE','FINAL_PREFLIGHT_REJECTED','SEND_WINDOW_EXPIRED') then
    raise exception 'Only sanitized error codes are permitted'; end if;
  if target='SUBMITTING' then
    if r.status<>'CLAIMED' or r.attempt_count<>0 then raise exception 'Submission already consumed'; end if;
    if (r.document->>'created_at')::timestamptz not between stamp-interval '120 seconds' and stamp
      or (r.document->>'risk_approved_at')::timestamptz not between stamp-interval '120 seconds' and stamp
      or preflight->>'decision' is distinct from 'APPROVED'
      or (preflight->>'at')::timestamptz not between stamp-interval '2 seconds' and stamp
      or coalesce(jsonb_array_length(preflight->'checks'),0)=0
      or exists(select 1 from jsonb_array_elements(preflight->'checks') g where g->>'passed' is distinct from 'true') then
      raise exception 'Fresh approved final preflight required'; end if;
    if r.document->>'classification'='PAPER' and
      (l.owner_id is distinct from worker or l.cycle_id is distinct from (r.document->>'cycle_id')::uuid
       or l.expires_at<stamp+interval '15 seconds') then raise exception 'Cycle lease lost or near expiry'; end if;
  elsif target='RECONCILING' then
    if r.status not in ('CLAIMED','SUBMITTING','SUBMITTED','RECONCILING','UNKNOWN') then
      raise exception 'Invalid reconciliation transition'; end if;
  elsif target='UNKNOWN' then
    if r.status='PENDING' then raise exception 'Unclaimed intent'; end if;
  elsif target in ('SUBMITTED','FILLED','CANCELED','REJECTED','EXPIRED') then
    if r.status='CLAIMED' and target='REJECTED' and broker is null and error_code is not null then
      null; -- Local fail-closed rejection before the submission claim.
    elsif r.status not in ('SUBMITTING','SUBMITTED','RECONCILING','UNKNOWN') or broker is null then
      raise exception 'Broker evidence required'; end if;
  else raise exception 'Invalid order transition'; end if;
  if broker is not null then
    if broker->>'client_order_id' is distinct from r.document->>'client_order_id'
      or broker->>'symbol' is distinct from r.document->'contracts'->>0
      or broker->>'classification' is distinct from r.document->>'classification'
      or broker->>'paper_mode' is distinct from 'true' or (broker->>'id')::uuid is null
      or (r.alpaca_order_id is not null and r.alpaca_order_id<>(broker->>'id')::uuid) then
      raise exception 'Broker identity mismatch'; end if;
  end if;
  update public.phase2_order_intents set status=target,
    attempt_count=r.attempt_count+case when target='SUBMITTING' then 1 else 0 end,
    submitted_at=coalesce(r.submitted_at,(broker->>'submitted_at')::timestamptz),
    reconciled_at=case when broker is not null or target='UNKNOWN' then stamp else r.reconciled_at end,
    alpaca_order_id=case when r.document->>'classification'='PAPER'
      then coalesce(r.alpaca_order_id,(broker->>'id')::uuid) else null end,
    broker_state=coalesce(broker,r.broker_state), last_error=error_code,
    owner_id=case when target in ('FILLED','CANCELED','REJECTED','EXPIRED','UNKNOWN','SUBMITTED') then null else worker end,
    claim_expires_at=case when target in ('FILLED','CANCELED','REJECTED','EXPIRED','UNKNOWN','SUBMITTED') then null
                         else stamp+interval '30 seconds' end,
    events=r.events||jsonb_build_array(jsonb_build_object('kind',target,'at',stamp,
      'classification',r.document->>'classification','error',error_code,'broker',broker,'preflight',preflight))
    where id=intent_id returning * into r;
  return to_jsonb(r);
end $$;
revoke all on function public.phase2_create_order_intent(jsonb,uuid) from public,anon,authenticated;
revoke all on function public.phase2_claim_order_intent(uuid,uuid) from public,anon,authenticated;
revoke all on function public.phase2_advance_order_intent(uuid,uuid,text,jsonb,text,jsonb) from public,anon,authenticated;
grant execute on function public.phase2_create_order_intent(jsonb,uuid) to service_role;
grant execute on function public.phase2_claim_order_intent(uuid,uuid) to service_role;
grant execute on function public.phase2_advance_order_intent(uuid,uuid,text,jsonb,text,jsonb) to service_role;
commit;
