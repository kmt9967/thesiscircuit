-- Transaction-scoped test changes to the NEW lease row only; all rolled back.
begin;
do $$
begin
 if not (select relrowsecurity from pg_class where oid='public.phase2_cycle_lease'::regclass)
 then raise exception 'RLS missing'; end if;
 if has_table_privilege('anon','public.phase2_cycle_lease','SELECT')
 or has_table_privilege('authenticated','public.phase2_cycle_lease','SELECT')
 or has_table_privilege('service_role','public.phase2_cycle_lease','UPDATE')
 then raise exception 'Unexpected direct access'; end if;
 if has_function_privilege('anon','public.phase2_acquire_lease(uuid,integer,uuid)','EXECUTE')
 or has_function_privilege('authenticated','public.phase2_release_lease(uuid,text,jsonb)','EXECUTE')
 or not has_function_privilege('service_role','public.phase2_acquire_lease(uuid,integer,uuid)','EXECUTE')
 or not has_function_privilege('service_role','public.phase2_release_lease(uuid,text,jsonb)','EXECUTE')
 then raise exception 'Unexpected function access'; end if;
end $$;
set local role anon;
do $$ begin
 begin perform * from public.phase2_cycle_lease; raise exception 'Anon read incorrectly allowed';
 exception when insufficient_privilege then null; end;
 begin perform public.phase2_acquire_lease(gen_random_uuid(),60,gen_random_uuid());
 raise exception 'Anon function incorrectly allowed'; exception when insufficient_privilege then null; end;
end $$;
reset role;
set local role service_role;
do $$ declare a uuid:='11111111-1111-4111-8111-111111111111';
 b uuid:='22222222-2222-4222-8222-222222222222'; c uuid:='33333333-3333-4333-8333-333333333333';
begin
 if not public.phase2_acquire_lease(a,60,c) then raise exception 'Acquisition failed'; end if;
 if not public.phase2_acquire_lease(a,60,c) then raise exception 'Owner retry not idempotent'; end if;
 if public.phase2_acquire_lease(b,60,c) then raise exception 'Overlap allowed'; end if;
 if public.phase2_release_lease(b,'FAILED') then raise exception 'Wrong owner release allowed'; end if;
 if not public.phase2_release_lease(a,'FAILED') then raise exception 'Release failed'; end if;
 if public.phase2_acquire_lease(b,60,c) then raise exception 'Cooldown bypass'; end if;
end $$;
reset role;
-- Simulate elapsed time inside this rolled-back test transaction.
update public.phase2_cycle_lease set next_allowed_at=clock_timestamp()-interval '1 second' where singleton=true;
set local role service_role;
select public.phase2_acquire_lease('22222222-2222-4222-8222-222222222222',60,
 '44444444-4444-4444-8444-444444444444') as abandoned_worker_acquired;
reset role;
update public.phase2_cycle_lease set expires_at=clock_timestamp()-interval '1 second',
 next_allowed_at=clock_timestamp()-interval '1 second' where singleton=true;
set local role service_role;
do $$ begin
 if not public.phase2_acquire_lease('55555555-5555-4555-8555-555555555555',60,
 '44444444-4444-4444-8444-444444444444') then raise exception 'Expiry recovery failed'; end if;
 if public.phase2_release_lease('22222222-2222-4222-8222-222222222222','FAILED')
 then raise exception 'Stale worker was not fenced'; end if;
 if not public.phase2_release_lease('55555555-5555-4555-8555-555555555555','FAILED')
 then raise exception 'Recovered release failed'; end if;
end $$;
reset role;
update public.phase2_cycle_lease set next_allowed_at=clock_timestamp()-interval '1 second' where singleton=true;
set local role service_role;
do $$ begin
 if public.phase2_acquire_lease(gen_random_uuid(),60,'44444444-4444-4444-8444-444444444444')
 then raise exception 'Retry cap bypassed'; end if;
end $$;
reset role;
select 'PASS: RLS, actual anon denial, server-only RPC, acquire, idempotent retry, overlap denial, release, cooldown, simulated expiry recovery, stale-owner fencing, retry cap' as verification;
rollback;
