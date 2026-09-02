-- Additive Phase 2 research. Phase 0 risk_decisions and all Phase 1 audit remain untouched.
begin;
create table if not exists public.autonomous_cycles (
  id uuid primary key, created_at timestamptz not null, batch text not null,
  sequence integer not null check (sequence between 0 and 2),
  payload jsonb not null check (payload->>'mode' = 'DRY_RUN' and payload->>'paper' = 'true'
    and payload->>'execution_enabled' = 'false'), unique(batch, sequence)
);
do $$
declare name text;
begin
  foreach name in array array['market_regimes','agent_runs','agent_proposals','critic_reviews',
    'allocation_decisions','phase2_risk_decisions','shadow_trades','shadow_marks','agent_scores',
    'position_reviews','reflections']
  loop
    execute format('create table if not exists public.%I (
      id uuid primary key default gen_random_uuid(),
      cycle_id uuid not null references public.autonomous_cycles(id),
      created_at timestamptz not null default now(), payload jsonb not null)', name);
    execute format('create index if not exists %I on public.%I (created_at desc)', name || '_recent', name);
    execute format('alter table public.%I enable row level security', name);
    execute format('revoke all on public.%I from anon, authenticated', name);
    execute format('grant select, insert on public.%I to service_role', name);
  end loop;
end $$;
alter table public.autonomous_cycles enable row level security;
revoke all on public.autonomous_cycles from anon, authenticated;
grant select, insert on public.autonomous_cycles to service_role;
create or replace function public.phase2_save_cycle(document jsonb) returns uuid
language plpgsql security definer set search_path = public, pg_temp as $$
declare
  cycle_id uuid := (document->>'id')::uuid;
  stamp timestamptz := (document->>'created_at')::timestamptz;
  key text; records jsonb; item jsonb;
begin
  if document->>'mode' is distinct from 'DRY_RUN'
     or document->>'paper' is distinct from 'true'
     or document->>'execution_enabled' is distinct from 'false' then
    raise exception 'Only paper dry-run documents are accepted';
  end if;
  insert into public.autonomous_cycles(id, created_at, batch, sequence, payload)
    values(cycle_id, stamp, document->>'batch', (document->>'sequence')::integer, document)
    on conflict (id) do nothing;
  if not found then return cycle_id; end if;
  insert into public.market_regimes(cycle_id, created_at, payload) values(cycle_id, stamp, document->'regime');
  insert into public.allocation_decisions(cycle_id, created_at, payload) values(cycle_id, stamp, document->'allocation');
  for key, records in select * from jsonb_each(jsonb_build_object(
    'agent_runs', document->'proposals', 'agent_proposals', document->'proposals',
    'critic_reviews', document->'critics', 'phase2_risk_decisions', document->'risk',
    'shadow_marks', document->'marks', 'agent_scores', document->'scores',
    'position_reviews', document->'position_reviews', 'reflections', document->'reflections'))
  loop
    for item in select * from jsonb_array_elements(records)
    loop
      execute format('insert into public.%I(cycle_id, created_at, payload) values ($1,$2,$3)', key)
        using cycle_id, stamp, item;
    end loop;
  end loop;
  for item in select * from jsonb_array_elements(document->'shadows')
  loop
    if item->>'classification' is distinct from 'COUNTERFACTUAL'
       or item->>'executed' is distinct from 'false' then
      raise exception 'Shadow must be non-executed counterfactual';
    end if;
    insert into public.shadow_trades(id, cycle_id, created_at, payload)
      values((item->>'id')::uuid, cycle_id, stamp, item);
  end loop;
  return cycle_id;
end $$;
revoke all on function public.phase2_save_cycle(jsonb) from public, anon, authenticated;
grant execute on function public.phase2_save_cycle(jsonb) to service_role;
commit;
