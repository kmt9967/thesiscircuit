-- Additive only: one new table, two new functions. Existing audit schema is preserved.
begin;
create table public.phase2_cycle_lease (
  singleton boolean primary key default true check(singleton),
  owner_id uuid, cycle_id uuid, expires_at timestamptz not null default '-infinity',
  next_allowed_at timestamptz not null default '-infinity',
  attempts jsonb not null default '{}', events jsonb not null default '[]'
);
insert into public.phase2_cycle_lease(singleton) values(true);
alter table public.phase2_cycle_lease enable row level security;
revoke all on public.phase2_cycle_lease from public, anon, authenticated, service_role;
grant select on public.phase2_cycle_lease to service_role;

create function public.phase2_acquire_lease(owner_id uuid, lease_seconds integer, requested_cycle uuid)
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare l public.phase2_cycle_lease; stamp timestamptz:=clock_timestamp(); n integer;
begin
  if owner_id is null or requested_cycle is null or lease_seconds is null or lease_seconds not between 60 and 180 then
    raise exception 'Invalid bounded lease'; end if;
  select * into l from public.phase2_cycle_lease where singleton for update;
  stamp:=clock_timestamp();
  if exists(select 1 from public.autonomous_cycles where id=requested_cycle) then return false; end if;
  if l.expires_at > stamp then
    return l.owner_id=phase2_acquire_lease.owner_id and l.cycle_id=requested_cycle;
  end if;
  if l.next_allowed_at > stamp then return false; end if;
  n:=coalesce((l.attempts->>requested_cycle::text)::integer,0);
  if n>=2 then return false; end if;
  if l.owner_id is not null then
    l.events:=l.events||jsonb_build_array(jsonb_build_object('kind','ABANDONED',
      'cycle_id',l.cycle_id,'at',stamp,'reason','lease_expired'));
  end if;
  update public.phase2_cycle_lease set owner_id=phase2_acquire_lease.owner_id,
    cycle_id=requested_cycle, expires_at=stamp+make_interval(secs=>lease_seconds),
    next_allowed_at=stamp+interval '60 seconds',
    attempts=jsonb_set(l.attempts,array[requested_cycle::text],to_jsonb(n+1)),
    events=l.events||jsonb_build_array(jsonb_build_object('kind','START',
      'cycle_id',requested_cycle,'at',stamp,'attempt',n+1)) where singleton;
  return true;
end $$;

create function public.phase2_release_lease(owner_id uuid, outcome text, document jsonb default null)
returns boolean language plpgsql security definer set search_path=public,pg_temp as $$
declare l public.phase2_cycle_lease; stamp timestamptz:=clock_timestamp();
begin
  select * into l from public.phase2_cycle_lease where singleton for update;
  stamp:=clock_timestamp();
  if owner_id is null then return false; end if;
  if l.owner_id is distinct from phase2_release_lease.owner_id or l.expires_at<=stamp then return false; end if;
  if outcome is null or outcome not in ('COMPLETED','FAILED','CANCELED') then raise exception 'Invalid terminal status'; end if;
  if outcome='COMPLETED' then
    if document is null or (document->>'id')::uuid is distinct from l.cycle_id then
      raise exception 'Cycle identity mismatch'; end if;
    perform public.phase2_save_cycle(document);
  elsif document is not null then raise exception 'Failure payload must not contain provider data';
  end if;
  update public.phase2_cycle_lease set owner_id=null, expires_at=stamp,
    next_allowed_at=greatest(next_allowed_at,stamp+interval '60 seconds'),
    events=l.events||jsonb_build_array(jsonb_build_object('kind',outcome,'cycle_id',l.cycle_id,'at',stamp))
    where singleton;
  return true;
end $$;
revoke all on function public.phase2_acquire_lease(uuid,integer,uuid) from public,anon,authenticated;
revoke all on function public.phase2_release_lease(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.phase2_acquire_lease(uuid,integer,uuid) to service_role;
grant execute on function public.phase2_release_lease(uuid,text,jsonb) to service_role;
commit;
