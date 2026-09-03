-- Read-only/rollback ACL verification; no fixture or historical mutation.
begin;
do $$
declare f text; role_name text;
begin
 if not (select relrowsecurity from pg_class where oid='public.phase2_execution_sessions'::regclass)
 then raise exception 'Session RLS missing'; end if;
 foreach role_name in array array['anon','authenticated'] loop
  if has_table_privilege(role_name,'public.phase2_execution_sessions','SELECT,INSERT,UPDATE,DELETE') then
   raise exception 'Frontend session access'; end if;
 end loop;
 if has_table_privilege('service_role','public.phase2_execution_sessions','INSERT,UPDATE,DELETE,TRUNCATE') then
  raise exception 'Service must use fenced session RPCs'; end if;
 foreach f in array array['phase2_create_execution_session(jsonb)',
   'phase2_session_control(uuid,text,text,uuid)','phase2_session_order_gate(uuid,uuid,uuid,text,jsonb)'] loop
  if has_function_privilege('anon','public.'||f,'EXECUTE')
   or has_function_privilege('authenticated','public.'||f,'EXECUTE')
   or not has_function_privilege('service_role','public.'||f,'EXECUTE') then
   raise exception 'Session function ACL incorrect'; end if;
 end loop;
end $$;
set local role anon;
do $$ begin
 begin perform * from public.phase2_execution_sessions; raise exception 'Anon read allowed';
 exception when insufficient_privilege then null; end;
 begin perform public.phase2_create_execution_session('{}'); raise exception 'Anon create allowed';
 exception when insufficient_privilege then null; end;
 begin perform public.phase2_session_control(gen_random_uuid(),'ACTIVATE'); raise exception 'Anon activate allowed';
 exception when insufficient_privilege then null; end;
 begin perform public.phase2_session_order_gate(gen_random_uuid(),gen_random_uuid(),gen_random_uuid(),'RESERVE');
  raise exception 'Anon budget allowed'; exception when insufficient_privilege then null; end;
end $$;
reset role;
select 'PASS: session RLS; anon/authenticated denied; service SELECT and three fenced RPCs only' as verification;
rollback;
