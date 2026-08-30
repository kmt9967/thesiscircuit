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

create table if not exists public.trade_proposals (
  id uuid primary key,
  trace_id uuid not null unique,
  created_at timestamptz not null default now(),
  symbol text not null,
  instrument text not null,
  asset_class text not null check (asset_class = 'us_option'),
  strategy_type text not null check (strategy_type = 'long_call'),
  side text not null check (side = 'buy'),
  quantity integer not null check (quantity = 1),
  order_type text not null check (order_type = 'limit'),
  time_in_force text not null check (time_in_force = 'day'),
  reference_price numeric not null,
  limit_price numeric not null,
  rationale text not null,
  invalidation text not null,
  confidence numeric not null,
  data_timestamp timestamptz not null,
  source text not null,
  estimated_max_loss numeric not null check (estimated_max_loss <= 250),
  status text not null,
  underlying text not null,
  expiry date not null,
  strike numeric not null,
  option_type text not null check (option_type = 'call'),
  legs jsonb not null,
  debit numeric not null,
  max_theoretical_loss numeric not null check (max_theoretical_loss <= 250),
  max_theoretical_gain text not null,
  breakeven numeric not null,
  liquidity_metrics jsonb not null,
  client_order_id text not null unique,
  paper boolean not null default true check (paper = true)
);

create table if not exists public.risk_checks (
  id uuid primary key,
  trace_id uuid not null unique,
  proposal_id uuid not null references public.trade_proposals(id),
  created_at timestamptz not null default now(),
  decision text not null check (decision in ('APPROVED','REJECTED')),
  checks jsonb not null,
  max_simulated_risk numeric not null check (max_simulated_risk <= 250)
);

create table if not exists public.decisions (
  id uuid primary key,
  trace_id uuid not null unique,
  proposal_id uuid not null references public.trade_proposals(id),
  created_at timestamptz not null default now(),
  decision text not null,
  reason text not null,
  paper boolean not null default true check (paper = true)
);

create table if not exists public.orders (
  alpaca_order_id text primary key,
  proposal_id uuid not null references public.trade_proposals(id),
  risk_check_id uuid not null references public.risk_checks(id),
  trace_id uuid not null unique,
  client_order_id text not null unique,
  submitted_at timestamptz not null,
  created_at timestamptz not null default now(),
  status text not null,
  instrument text not null,
  quantity numeric not null check (quantity = 1),
  filled_quantity numeric not null default 0,
  filled_average_price numeric,
  filled_at timestamptz,
  paper boolean not null default true check (paper = true)
);

create table if not exists public.fills (
  id uuid primary key default gen_random_uuid(),
  trace_id uuid not null,
  order_id text not null references public.orders(alpaca_order_id),
  created_at timestamptz not null default now(),
  instrument text not null,
  quantity numeric not null,
  price numeric not null,
  filled_at timestamptz not null,
  paper boolean not null default true check (paper = true),
  unique (order_id, filled_at)
);

create table if not exists public.positions_snapshots (
  id uuid primary key default gen_random_uuid(),
  trace_id uuid not null,
  created_at timestamptz not null default now(),
  instrument text not null,
  position jsonb,
  account jsonb not null,
  paper boolean not null default true check (paper = true)
);

create table if not exists public.system_events (
  id uuid primary key default gen_random_uuid(),
  trace_id uuid not null,
  sequence integer not null,
  created_at timestamptz not null default now(),
  kind text not null,
  payload jsonb not null,
  paper boolean not null default true check (paper = true),
  unique (trace_id, sequence)
);

alter table public.trade_proposals enable row level security;
alter table public.risk_checks enable row level security;
alter table public.decisions enable row level security;
alter table public.orders enable row level security;
alter table public.fills enable row level security;
alter table public.positions_snapshots enable row level security;
alter table public.system_events enable row level security;

grant select, insert, update, delete on
  public.trade_proposals,
  public.risk_checks,
  public.decisions,
  public.orders,
  public.fills,
  public.positions_snapshots,
  public.system_events
to service_role;
