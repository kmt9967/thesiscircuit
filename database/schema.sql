create extension if not exists pgcrypto;

create table if not exists public.analysis_runs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  symbol text not null,
  strategy text not null,
  mode text not null default 'paper' check (mode = 'paper'),
  order_submission_enabled boolean not null default false check (order_submission_enabled = false)
);

create table if not exists public.agent_votes (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.analysis_runs(id) on delete cascade,
  role text not null,
  stance text not null,
  confidence numeric not null check (confidence between 0 and 1),
  rationale text not null
);

create table if not exists public.risk_decisions (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.analysis_runs(id) on delete cascade,
  approved_for_research boolean not null,
  vetoes jsonb not null default '[]'::jsonb
);

create table if not exists public.replay_events (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.analysis_runs(id) on delete cascade,
  sequence integer not null,
  kind text not null,
  payload jsonb not null,
  unique (run_id, sequence)
);

alter table public.analysis_runs enable row level security;
alter table public.agent_votes enable row level security;
alter table public.risk_decisions enable row level security;
alter table public.replay_events enable row level security;

-- No public policies are created in Phase 0. Backend service-role access only.
grant select, insert, update, delete on
  public.analysis_runs,
  public.agent_votes,
  public.risk_decisions,
  public.replay_events
to service_role;
