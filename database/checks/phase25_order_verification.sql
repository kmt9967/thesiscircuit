-- Protocol-only fixtures. No broker calls. All test rows and expiry changes roll back.
begin;
do $$
declare f text; role_name text;
begin
 if not (select relrowsecurity from pg_class where oid='public.phase2_order_intents'::regclass)
 then raise exception 'RLS missing'; end if;
 foreach role_name in array array['anon','authenticated'] loop
  if has_table_privilege(role_name,'public.phase2_order_intents','SELECT,INSERT,UPDATE,DELETE') then
   raise exception 'Frontend table access'; end if;
 end loop;
 if has_table_privilege('service_role','public.phase2_order_intents','INSERT,UPDATE,DELETE,TRUNCATE') then
  raise exception 'Service must use fenced RPCs, not direct mutation'; end if;
 foreach f in array array['phase2_create_order_intent(jsonb,uuid)','phase2_claim_order_intent(uuid,uuid)',
   'phase2_advance_order_intent(uuid,uuid,text,jsonb,text,jsonb)'] loop
  if has_function_privilege('anon','public.'||f,'EXECUTE')
   or has_function_privilege('authenticated','public.'||f,'EXECUTE')
   or not has_function_privilege('service_role','public.'||f,'EXECUTE') then
    raise exception 'Function ACL incorrect'; end if;
 end loop;
end $$;
set local role anon;
do $$ begin
 begin perform * from public.phase2_order_intents; raise exception 'Anon read allowed';
 exception when insufficient_privilege then null; end;
 begin perform public.phase2_claim_order_intent(gen_random_uuid(),gen_random_uuid()); raise exception 'Anon RPC allowed';
 exception when insufficient_privilege then null; end;
end $$;
reset role;
set local role service_role;
do $$
declare a uuid:='aaaaaaaa-2525-4252-8252-aaaaaaaaaaaa';
 b uuid:='bbbbbbbb-2525-4252-8252-bbbbbbbbbbbb';
 i uuid:='cccccccc-2525-4252-8252-cccccccccccc';
 d jsonb; r jsonb; n integer;
begin
 d:=jsonb_build_object('id',i,'cycle_id',i,'proposal_id',i,'risk_decision_id',i,'action','OPEN',
  'underlying','SPY','contracts',jsonb_build_array('SPY260904C00700000'),'side','buy','quantity',1,
  'order_type','limit','time_in_force','day','limit_price','1.05','client_order_id','tc-p2-'||i,
  'expected_max_loss','105','created_at',clock_timestamp(),'risk_approved_at',clock_timestamp(),
  'paper_mode',true,'classification','SYNTHETIC','proposal',jsonb_build_object('id',i),
  'risk',jsonb_build_object('proposal_id',i,'decision','APPROVED','checks',jsonb_build_array(
    jsonb_build_object('name','SYNTHETIC_PROTOCOL_ONLY','passed',true))));
 r:=public.phase2_create_order_intent(d,a);
 if r->>'status'<>'PENDING' then raise exception 'Persistence failed'; end if;
 if public.phase2_create_order_intent(d,a)<>r then raise exception 'Duplicate persistence changed state'; end if;
 begin perform public.phase2_create_order_intent(jsonb_set(d,'{limit_price}','"9"'),a);
  raise exception 'Immutable mutation allowed'; exception when raise_exception then
  if sqlerrm<>'Immutable intent conflict' then raise; end if; end;
 r:=public.phase2_claim_order_intent(i,a);
 if r->>'status'<>'CLAIMED' then raise exception 'Claim failed'; end if;
 begin perform public.phase2_claim_order_intent(i,b); raise exception 'Second worker acquired';
 exception when raise_exception then if sqlerrm<>'Intent already claimed' then raise; end if; end;
 r:=public.phase2_advance_order_intent(i,a,'SUBMITTING',null,null,jsonb_build_object('at',clock_timestamp(),
  'decision','APPROVED','checks',jsonb_build_array(jsonb_build_object('passed',true))));
 if (r->>'attempt_count')::int<>1 then raise exception 'Submission count'; end if;
 begin perform public.phase2_advance_order_intent(i,a,'SUBMITTING'); raise exception 'Double submission allowed';
 exception when raise_exception then if sqlerrm<>'Submission already consumed' then raise; end if; end;
 n:=jsonb_array_length(r->'events');
 if n<>3 then raise exception 'Missing audit events'; end if;
end $$;
reset role;
-- Controlled timestamp advancement only on the new synthetic fixture, rolled back.
update public.phase2_order_intents set claim_expires_at=clock_timestamp()-interval '1 second'
 where id='cccccccc-2525-4252-8252-cccccccccccc';
set local role service_role;
do $$
declare a uuid:='aaaaaaaa-2525-4252-8252-aaaaaaaaaaaa'; b uuid:='bbbbbbbb-2525-4252-8252-bbbbbbbbbbbb';
 i uuid:='cccccccc-2525-4252-8252-cccccccccccc'; r jsonb; broker jsonb;
begin
 r:=public.phase2_claim_order_intent(i,b);
 if r->>'status'<>'SUBMITTING' or (r->>'attempt_count')::int<>1 then raise exception 'Restart reset submission'; end if;
 begin perform public.phase2_advance_order_intent(i,a,'RECONCILING'); raise exception 'Stale worker allowed';
 exception when raise_exception then if sqlerrm<>'Order claim lost' then raise; end if; end;
 perform public.phase2_advance_order_intent(i,b,'RECONCILING');
 perform public.phase2_advance_order_intent(i,b,'UNKNOWN',null,'RECONCILIATION_REQUIRED');
 perform public.phase2_claim_order_intent(i,a);
 begin perform public.phase2_advance_order_intent(i,a,'SUBMITTING'); raise exception 'Unknown resubmitted';
 exception when raise_exception then if sqlerrm<>'Submission already consumed' then raise; end if; end;
 perform public.phase2_advance_order_intent(i,a,'RECONCILING');
 broker:=jsonb_build_object('id',i,'client_order_id','tc-p2-'||i,'symbol','SPY260904C00700000',
  'paper_mode',true,'classification','SYNTHETIC','status','filled','filled_qty','1','filled_avg_price','1.04',
  'submitted_at',clock_timestamp());
 r:=public.phase2_advance_order_intent(i,a,'FILLED',broker);
 if r->>'alpaca_order_id' is not null then raise exception 'Synthetic reference became Alpaca order'; end if;
 if public.phase2_claim_order_intent(i,b)<>r then raise exception 'Completed replay changed state'; end if;
end $$;
reset role;
select 'PASS: RLS, anon RPC denial, service-only mutation, immutable intent, duplicate claim denial, one submission transition, SUBMITTING recovery, stale worker fencing, UNKNOWN never resubmits, terminal replay, synthetic separation' as verification;
rollback;
