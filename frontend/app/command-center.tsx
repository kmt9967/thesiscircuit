"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Navigation from "./navigation";

type Account = { equity: number; cash: number; buying_power: number; competition_pnl: number };
type Quote = { symbol: string; underlying: string; bid: number; ask: number; quote_at: string; source: string; expiry: string; strike?: number; kind?: string; tradable?: boolean; open_interest?: number | null; implied_volatility?: number | null; delta?: number | null; gamma?: number | null; theta?: number | null; vega?: number | null };
type Position = { symbol: string; qty: number; entry: number; current_price: number; market_value: number; unrealized_pl: number; unrealized_plpc: number };
type PositionReview = { timestamp: string; recommendation: string; reasons: string[]; hours_to_expiry: number | null; theta_daily_dollars: number | null; quote: Quote | null; quote_fresh?: boolean; mark_basis?: string; position: Position };
type Portfolio = { observed_at: string; market_open: boolean; account: Account; total_orders: number; positions: PositionReview[] };
type Proposal = { id: string; agent: string; thesis: string; confidence: number; estimated_max_loss: number; status: string; strategy_type?: string; contract: Quote | null; reasons_not_to_trade: string[]; timestamp?: string };
type Critic = { proposal_id: string; strongest_counterargument: string; concentration_risk: string; no_trade_argument: string };
type RiskCheck = { name: string; passed: boolean; reason: string };
type Risk = { proposal_id: string; decision: string; reasons: string[]; checks: RiskCheck[] };
type Score = { agent: string; score: number; shadow_samples: number; shadow_pnl: number | null; executed_realized_pnl: number | null; basis: string };
type Shadow = { id: string; agent: string; symbol: string; timestamp: string; entry_reference: number; rejection_reason: string; hypothetical_max_loss: number };
type Mark = { shadow_id: string; timestamp: string; hypothetical_pnl: number; decision_regret: number; rejection_effect: string; horizon_complete: boolean };
type Cycle = { id: string; created_at: string; decision: string; regime: { name: string; confidence: number; metrics: Record<string, number | null>; timestamp?: string; invalidation?: string }; proposals: Proposal[]; critics: Critic[]; risk: Risk[]; scores: Score[]; allocation: { decision: string; reason: string; proposal_id: string | null }; position_reviews: PositionReview[]; state: { data_errors: string[]; observations?: Quote[]; clock?: { is_open: boolean }; account?: Record<string, unknown> }; timeline: { sequence: number; stage: string; timestamp: string }[] };
type Phase2Data = { database_connected: boolean; latest: Cycle | null; execution_enabled: false; batch_status: { status: string }; dispatcher?: { mode: string; broker_dispatch_available: boolean; events: Array<{ at: string; kind: string; cycle_id: string }> }; shadows: Shadow[]; marks: Mark[]; cycles: { id: string; created_at: string; decision: string }[] };
type Phase1Data = { generated_at: string; execution_enabled: boolean; integrations: Record<string, boolean>; latest_proposal: Record<string, unknown> | null; latest_risk: Record<string, unknown> | null; latest_order: Record<string, unknown> | null; latest_fill: Record<string, unknown> | null; latest_position: Record<string, unknown> | null; timeline: Array<Record<string, unknown>> };
type Bundle = { phase1: Phase1Data | null; phase2: Phase2Data | null; portfolio: Portfolio | null };

const apiBase = "/backend";
const money = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? "Unavailable" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
const percent = (value: number | null | undefined, digits = 1) => value == null || !Number.isFinite(value) ? "Unavailable" : `${value.toFixed(digits)}%`;
const when = (value: unknown) => typeof value === "string" && value ? new Date(value).toLocaleString() : "Unavailable";
const label = (value: unknown, fallback = "Unavailable") => typeof value === "string" && value ? value : fallback;
const numeric = (value: unknown) => typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : null;
const shortId = (value: unknown) => typeof value === "string" && value.length > 13 ? `${value.slice(0, 8)}…${value.slice(-4)}` : label(value);

function optionIdentity(symbol: string) {
  const match = symbol.match(/^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$/);
  if (!match) return { friendly: symbol, contract: symbol };
  const [, root, year, month, day, kind, strikeRaw] = match;
  const strike = Number(strikeRaw) / 1000;
  const date = new Date(Date.UTC(2000 + Number(year), Number(month) - 1, Number(day)));
  const expiry = date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
  return { friendly: `${root} ${expiry} $${strike.toLocaleString()} ${kind === "C" ? "Call" : "Put"}`, contract: symbol };
}

function Kicker({ children }: { children: React.ReactNode }) { return <p className="kicker"><span />{children}</p>; }
function Pill({ children, tone = "cyan" }: { children: React.ReactNode; tone?: "cyan" | "green" | "amber" | "red" | "muted" }) { return <span className={`pill ${tone}`}>{children}</span>; }
function Metric({ name, value, detail, tone }: { name: string; value: string; detail?: string; tone?: string }) {
  return <article className="metric-card"><span>{name}</span><strong className={tone}>{value}</strong>{detail ? <small>{detail}</small> : null}</article>;
}
function SectionHead({ eyebrow, title, copy, aside }: { eyebrow: string; title: string; copy: string; aside?: React.ReactNode }) {
  return <header className="section-head"><div><Kicker>{eyebrow}</Kicker><h2>{title}</h2><p>{copy}</p></div>{aside ? <div className="section-aside">{aside}</div> : null}</header>;
}
function EmptyState({ title, copy }: { title: string; copy: string }) { return <div className="empty-state"><span aria-hidden="true">◇</span><strong>{title}</strong><p>{copy}</p></div>; }
function Progress({ value, tone = "cyan" }: { value: number; tone?: string }) { return <div className="progress" aria-label={`${value.toFixed(0)} percent`}><i className={tone} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div>; }

const workflow = [
  ["01", "Market data", "Alpaca account, clock, bars, and option snapshots"],
  ["02", "Feature engine", "Deterministic freshness and regime inputs"],
  ["03", "Strategy agents", "Trend, Range, and Defensive theses"],
  ["04", "Critic", "Adversarial objections and concentration checks"],
  ["05", "Allocator", "Select a thesis or preserve cash"],
  ["06", "Risk officer", "Non-overridable deterministic gates"],
  ["07", "Paper execution", "Durable, bounded, currently disabled"],
] as const;

export default function CommandCenter() {
  const [bundle, setBundle] = useState<Bundle>({ phase1: null, phase2: null, portfolio: null });
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [refreshIndex, setRefreshIndex] = useState(0);
  const [active, setActive] = useState("overview");

  const load = useCallback(async (signal: AbortSignal) => {
    setLoading(true);
    const endpoints = ["/phase1/dashboard", "/phase2/dashboard", "/phase2/portfolio"] as const;
    const results = await Promise.allSettled(endpoints.map(async endpoint => {
      const response = await fetch(`${apiBase}${endpoint}`, { cache: "no-store", signal });
      if (!response.ok) throw new Error(`${endpoint} returned ${response.status}`);
      return response.json() as Promise<unknown>;
    }));
    if (signal.aborted) return;
    const nextErrors: string[] = [];
    results.forEach((result, index) => { if (result.status === "rejected") nextErrors.push(result.reason instanceof Error ? result.reason.message : `${endpoints[index]} unavailable`); });
    setErrors(nextErrors);
    setBundle(previous => ({
      phase1: results[0].status === "fulfilled" ? results[0].value as Phase1Data : previous.phase1,
      phase2: results[1].status === "fulfilled" ? results[1].value as Phase2Data : previous.phase2,
      portfolio: results[2].status === "fulfilled" ? results[2].value as Portfolio : previous.portfolio,
    }));
    setLoading(false);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15000);
    void load(controller.signal).finally(() => window.clearTimeout(timeout));
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [load, refreshIndex]);

  useEffect(() => {
    const ids = ["overview", "market", "regime", "arena", "council", "risk", "position", "original-trade", "shadow", "leaderboard", "cycles", "audit", "architecture"];
    const observer = new IntersectionObserver(entries => {
      const visible = entries.find(entry => entry.isIntersecting);
      if (visible) setActive(visible.target.id);
    }, { rootMargin: "-18% 0px -68%", threshold: 0 });
    ids.forEach(id => { const element = document.getElementById(id); if (element) observer.observe(element); });
    return () => observer.disconnect();
  }, []);

  const navigate = useCallback((id: string) => {
    const element = document.getElementById(id);
    if (!element) return;
    const top = element.getBoundingClientRect().top + window.scrollY - 82;
    window.scrollTo({ top, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, []);

  const cycle = bundle.phase2?.latest;
  const portfolio = bundle.portfolio;
  const account = portfolio?.account;
  const pnlPercent = account ? account.competition_pnl / 1000 : null;
  const position = portfolio?.positions[0];
  const observations = cycle?.state.observations ?? [];
  const order = bundle.phase1?.latest_order;
  const fill = bundle.phase1?.latest_fill;
  const latestProposal = bundle.phase1?.latest_proposal;
  const latestRisk = bundle.phase1?.latest_risk;
  const orderSymbol = label(order?.instrument, position?.position.symbol ?? "");
  const originalIdentity = optionIdentity(orderSymbol || "Option contract unavailable");
  const currentIdentity = position ? optionIdentity(position.position.symbol) : null;
  const scores = useMemo(() => [...(cycle?.scores ?? [])].sort((a, b) => b.score - a.score), [cycle]);

  return <div className="app-shell">
    <Navigation active={active} onNavigate={navigate} />
    <main>
      <section className="hero-section quant-grid" id="overview">
        <div className="hero-glow" />
        <div className="content hero-grid">
          <div className="hero-copy reveal">
            <Kicker>ALPACA PAPER · AUTONOMOUS OPTIONS RESEARCH</Kicker>
            <h1>Competing theses.<br /><em>Accountable decisions.</em></h1>
            <p>Three strategy agents challenge the same market. A critic questions every thesis. Deterministic risk gets the final veto—and every refusal leaves evidence.</p>
            <div className="hero-actions"><button onClick={() => navigate("arena")}>Explore the arena <span>→</span></button><button className="ghost" onClick={() => navigate("original-trade")}>View verified fill</button></div>
            <div className="safety-row"><Pill tone="green">PAPER ONLY</Pill><Pill tone="muted">EXECUTION DISABLED</Pill><Pill tone="muted">AUTONOMY DISABLED</Pill><Pill tone="red">LIVE BLOCKED</Pill></div>
          </div>
          <aside className="command-card reveal delay-one" aria-label="Competition account overview">
            <div className="command-head"><div><span>COMPETITION ACCOUNT</span><b>ACTUAL ALPACA PAPER RESULTS</b></div><span className="radar"><i /></span></div>
            {account ? <>
              <p className="command-label">Official account equity</p><strong className="hero-equity">{money(account.equity)}</strong>
              <div className="pnl-line"><span className={account.competition_pnl >= 0 ? "positive" : "negative"}>{account.competition_pnl >= 0 ? "+" : ""}{money(account.competition_pnl)}</span><small>vs $100,000 starting equity · {percent(pnlPercent)}</small></div>
              <div className="command-metrics"><div><span>Cash</span><b>{money(account.cash)}</b></div><div><span>Buying power</span><b>{money(account.buying_power)}</b></div><div><span>Positions</span><b>{portfolio?.positions.length ?? 0}</b></div><div><span>Orders</span><b>{portfolio?.total_orders ?? 0}</b></div></div>
              <p className="as-of">Broker read {when(portfolio?.observed_at)} · Market {portfolio?.market_open ? "OPEN" : "CLOSED"}</p>
            </> : <EmptyState title={loading ? "Connecting to Alpaca PAPER" : "Account state unavailable"} copy="No account value is invented while the broker read is unavailable." />}
          </aside>
        </div>
      </section>

      <section className="workflow-strip" aria-label="Autonomous decision workflow"><div className="content workflow-row">{workflow.map(([step, name, description], index) => <article key={step}><span>{step}</span><div><b>{name}</b><small>{description}</small></div>{index < workflow.length - 1 ? <i aria-hidden="true">→</i> : null}</article>)}</div></section>

      {errors.length ? <div className="content api-alert" role="alert"><div><b>Partial live-data interruption</b><p>{errors.join(" · ")}. Previously verified records remain labelled with their timestamps.</p></div><button onClick={() => setRefreshIndex(value => value + 1)}>Retry reads</button></div> : null}

      <section className="section" id="market"><div className="content">
        <SectionHead eyebrow="LIVE BROKER OBSERVATIONS" title="Market intelligence" copy="Source-labelled Alpaca option snapshots. Stale observations remain visible for evidence but cannot authorize execution." aside={<Pill tone={portfolio?.market_open ? "green" : "amber"}>MARKET {portfolio?.market_open ? "OPEN" : "CLOSED"}</Pill>} />
        {observations.length ? <div className="market-grid">{observations.map(quote => { const identity = optionIdentity(quote.symbol); const mid = (quote.bid + quote.ask) / 2; const spread = quote.ask - quote.bid; return <article className="data-card" key={quote.symbol}><div className="card-top"><div><b>{identity.friendly}</b><code>{identity.contract}</code></div><Pill tone={quote.tradable ? "green" : "red"}>{quote.tradable ? "TRADABLE" : "BLOCKED"}</Pill></div><div className="quote-price"><strong>{money(mid)}</strong><span>indicative midpoint</span></div><div className="data-grid"><div><span>Bid / ask</span><b>{money(quote.bid)} / {money(quote.ask)}</b></div><div><span>Spread</span><b>{money(spread)}</b></div><div><span>Open interest</span><b>{quote.open_interest?.toLocaleString() ?? "Unavailable"}</b></div><div><span>Implied vol</span><b>{quote.implied_volatility == null ? "Unavailable" : percent(quote.implied_volatility * 100)}</b></div></div><p className="as-of">{quote.source} · {when(quote.quote_at)}</p></article>; })}</div> : <EmptyState title="No eligible current option snapshots" copy="The backend returned no current contract observations. ThesisCircuit will not substitute prototype prices." />}
      </div></section>

      <section className="section alternate" id="regime"><div className="content">
        <SectionHead eyebrow="DETERMINISTIC FEATURE ENGINE" title="Market regime" copy="A rule-based classification recomputed each cycle. Missing or stale inputs resolve to uncertainty, not confidence theater." />
        {cycle ? <div className="regime-layout"><article className="regime-primary"><span>ACTIVE CLASSIFICATION</span><h3>{cycle.regime.name.replaceAll("_", " ")}</h3><div><b>{percent(cycle.regime.confidence * 100, 0)}</b><small>heuristic confidence · not a probability</small></div><Progress value={cycle.regime.confidence * 100} tone="cyan" /><p>{cycle.regime.invalidation ?? "Recomputed on every research cycle."}</p></article><div className="regime-metrics">{Object.keys(cycle.regime.metrics).length ? Object.entries(cycle.regime.metrics).map(([name, value]) => <Metric key={name} name={name.replaceAll("_", " ")} value={value == null ? "Unavailable" : value.toFixed(4)} />) : <EmptyState title="Feature values unavailable" copy={cycle.state.data_errors.join(" · ") || "The classifier did not receive a complete fresh feature set."} />}</div></div> : <EmptyState title="No completed research cycle" copy="Regime state will appear only from a recorded backend cycle." />}
      </div></section>

      <section className="section" id="arena"><div className="content">
        <SectionHead eyebrow="MULTI-AGENT OPTIONS ENGINE" title="Strategy arena" copy="Three independent theses compete on the same recorded state. Capital allocation remains zero unless every hurdle clears." aside={<button className="refresh-button" onClick={() => setRefreshIndex(value => value + 1)} disabled={loading}>{loading ? "Refreshing…" : "Refresh state"}</button>} />
        {cycle ? <><p className="recorded-line">Recorded {when(cycle.created_at)} · finite batch {bundle.phase2?.batch_status.status} · not a live price stream</p><div className="agent-grid">{cycle.proposals.map(proposal => { const score = cycle.scores.find(item => item.agent === proposal.agent); return <article className="agent-panel" key={proposal.id}><div className="agent-head"><div><span>{proposal.agent}</span><small>STRATEGY AGENT</small></div><Pill tone={proposal.status === "NO_TRADE" ? "amber" : "cyan"}>{proposal.status.replaceAll("_", " ")}</Pill></div><h3>{proposal.contract ? optionIdentity(proposal.contract.symbol).friendly : "Capital stays in cash"}</h3>{proposal.contract ? <code>{proposal.contract.symbol}</code> : null}<p>{proposal.thesis}</p><div className="agent-stats"><div><span>Confidence</span><b>{percent(proposal.confidence * 100, 0)}</b><Progress value={proposal.confidence * 100} /></div><div><span>Risk budget</span><b>{money(proposal.estimated_max_loss)}</b></div><div><span>Evidence score</span><b>{score?.score.toFixed(2) ?? "Unavailable"}</b></div><div><span>Shadow samples</span><b>{score?.shadow_samples ?? 0}</b></div></div><details><summary>Inspect thesis and objections</summary><p>{proposal.reasons_not_to_trade.join(" · ") || "No rejection reason recorded."}</p><small>Shadow P&amp;L: {money(score?.shadow_pnl)} · executed attribution: {money(score?.executed_realized_pnl)}</small></details></article>; })}</div></> : <EmptyState title="No completed agent cycle" copy="No strategy state is fabricated while the research ledger is unavailable." />}
      </div></section>

      <section className="section alternate" id="council"><div className="content">
        <SectionHead eyebrow="ADVERSARIAL GOVERNANCE" title="Decision council" copy="Agent proposals flow through an independent critic, allocator, and deterministic risk officer." aside={<Pill tone="amber">{cycle?.decision?.replaceAll("_", " ") ?? "NO RECORD"}</Pill>} />
        {cycle ? <div className="council-flow"><div className="council-proposals">{cycle.proposals.map(proposal => <article key={proposal.id}><span>{proposal.agent}</span><b>{proposal.status.replaceAll("_", " ")}</b><p>{proposal.thesis}</p></article>)}</div><div className="flow-arrow">↓</div><article className="critic-card"><span>STAGE 2 · ADVERSARIAL CRITIC</span><div>{cycle.critics.map(critic => <p key={critic.proposal_id}>“{critic.strongest_counterargument} {critic.concentration_risk}”</p>)}</div></article><div className="flow-arrow">↓</div><article className="allocator-card"><span>STAGE 3 · META ALLOCATOR</span><b>{cycle.allocation.decision.replaceAll("_", " ")}</b><p>{cycle.allocation.reason}</p></article><div className="flow-arrow">↓</div><article className="verdict-card"><span>FINAL SYSTEM ACTION</span><h3>{cycle.decision.replaceAll("_", " ")}</h3><p>{cycle.risk.every(item => item.decision === "REJECTED") ? "Risk rejected every candidate. No broker dispatch occurred." : "See the recorded risk decision for authorization state."}</p></article></div> : <EmptyState title="Council record unavailable" copy="No debate or verdict is synthesized without backend evidence." />}
      </div></section>

      <section className="section" id="position"><div className="content">
        <SectionHead eyebrow="ACTUAL ALPACA PAPER POSITION" title="Position watch" copy="Broker-reported valuation and source-labelled option metrics. Recommendations are research only; closing authority is disabled." aside={<Pill tone="red">NO CLOSING AUTHORITY</Pill>} />
        {position && currentIdentity ? <article className="position-card"><div className="position-title"><div><Pill tone="green">LONG {position.position.qty} CONTRACT</Pill><h3>{currentIdentity.friendly}</h3><code>{currentIdentity.contract}</code></div><div><span>Research recommendation</span><b>{position.recommendation} · NOT EXECUTED</b></div></div><div className="metric-grid"><Metric name="Entry" value={money(position.position.entry)} /><Metric name="Broker value" value={money(position.position.market_value)} /><Metric name="Unrealized P&L" value={money(position.position.unrealized_pl)} detail={percent(position.position.unrealized_plpc * 100, 2)} tone={position.position.unrealized_pl >= 0 ? "positive" : "negative"} /><Metric name="Current mark" value={money(position.position.current_price)} /><Metric name="Time to expiry" value={position.hours_to_expiry == null ? "Unavailable" : `${position.hours_to_expiry.toFixed(1)}h`} /><Metric name="Theta / day" value={money(position.theta_daily_dollars)} detail="model estimate" /></div>{position.quote ? <div className="greeks-row">{[["Delta", position.quote.delta], ["Gamma", position.quote.gamma], ["Theta", position.quote.theta], ["Vega", position.quote.vega]].map(([name, value]) => <div key={String(name)}><span>{name}</span><b>{typeof value === "number" ? value.toFixed(4) : "Unavailable"}</b></div>)}</div> : null}<div className="risk-note"><b>{position.reasons.join(" · ")}</b><span>{position.mark_basis}. Quote {position.quote_fresh ? "fresh" : "stale / not eligible for execution"} at {when(position.quote?.quote_at)}.</span></div></article> : <EmptyState title="No open paper position" copy="Only an actual broker-reported position can populate this panel." />}
      </div></section>

      <section className="section alternate" id="original-trade"><div className="content">
        <SectionHead eyebrow="PRESERVED PHASE 1 EVIDENCE" title="The original paper trade" copy="One controlled opening order, reconciled from Alpaca and persisted in Supabase. No additional or closing order was sent." aside={<Pill tone="green">{label(order?.status, "NO ORDER").toUpperCase()}</Pill>} />
        {order ? <div className="trade-layout"><article className="trade-ticket"><span>VERIFIED ALPACA PAPER FILL</span><h3>{originalIdentity.friendly}</h3><code>{originalIdentity.contract}</code><div className="trade-values"><div><span>Action</span><b>BUY TO OPEN</b></div><div><span>Quantity</span><b>{String(order.quantity ?? "Unavailable")}</b></div><div><span>Order</span><b>{label(latestProposal?.time_in_force, "DAY").toUpperCase()} {label(latestProposal?.order_type, "LIMIT").toUpperCase()}</b></div><div><span>Limit</span><b>{money(numeric(latestProposal?.limit_price))}</b></div><div><span>Actual fill</span><b className="positive">{money(numeric(fill?.price ?? order.filled_average_price))}</b></div><div><span>Max planned risk</span><b>{money(numeric(latestRisk?.max_simulated_risk))}</b></div></div><p>Order reference <code>{shortId(order.alpaca_order_id)}</code> · PAPER only</p></article><ol className="trade-timeline">{bundle.phase1?.timeline.map((event, index) => <li key={String(event.id ?? index)}><i>{String(index + 1).padStart(2, "0")}</i><div><b>{label(event.kind).replaceAll("_", " ")}</b><span>{when(event.created_at)}</span></div></li>)}</ol></div> : <EmptyState title="No reconciled Alpaca order" copy="Readiness records are never presented as executed orders." />}
      </div></section>

      <section className="section" id="risk"><div className="content">
        <SectionHead eyebrow="DETERMINISTIC CAPITAL GOVERNOR" title="Risk engine" copy="The agent layer cannot override these checks. Any blocked or unknown condition prevents broker dispatch." aside={<Pill tone="red">FAIL CLOSED</Pill>} />
        {cycle?.risk.length ? <><div className="risk-summary"><div><span>Current council result</span><b>{cycle.decision.replaceAll("_", " ")}</b></div><div><span>Candidate evaluations</span><b>{cycle.risk.length}</b></div><div><span>Broker dispatch</span><b>0 · DISABLED</b></div></div><div className="gate-grid">{cycle.risk[0].checks.map(check => <article key={check.name} className={check.passed ? "pass" : "blocked"}><span>{check.passed ? "✓" : "×"}</span><div><b>{check.name.replaceAll("_", " ")}</b><p>{check.reason}</p></div><Pill tone={check.passed ? "green" : "red"}>{check.passed ? "PASS" : "BLOCK"}</Pill></article>)}</div></> : <EmptyState title="Risk record unavailable" copy="An absent risk decision never implies approval." />}
      </div></section>

      <section className="section alternate" id="shadow"><div className="content">
        <SectionHead eyebrow="COUNTERFACTUAL · NEVER SENT TO ALPACA" title="Shadow desk" copy="Rejected ideas are marked against later observed bids to measure decision quality without claiming fills, fees, or executable returns." aside={<Pill tone="muted">NOT EXECUTED</Pill>} />
        {bundle.phase2?.shadows.length ? <div className="shadow-grid">{bundle.phase2.shadows.map(shadow => { const mark = bundle.phase2?.marks.find(item => item.shadow_id === shadow.id); const identity = optionIdentity(shadow.symbol); return <article className="shadow-card" key={shadow.id}><div><Pill tone="muted">{shadow.agent}</Pill><Pill tone="amber">NOT EXECUTED</Pill></div><h3>{identity.friendly}</h3><code>{identity.contract}</code><p>{shadow.rejection_reason}</p><div className="shadow-values"><span>Reference ask <b>{money(shadow.entry_reference)}</b></span><span>Max hypothetical risk <b>{money(shadow.hypothetical_max_loss)}</b></span><span>Later mark outcome <b>{money(mark?.hypothetical_pnl)}</b></span><span>Decision effect <b>{mark?.rejection_effect ?? "Unmeasured"}</b></span></div><small>{mark ? `${mark.horizon_complete ? "Completed horizon" : "Interim observation"} · ${when(mark.timestamp)}` : "Awaiting a later eligible observation"}</small></article>; })}</div> : <EmptyState title="No shadow records" copy="The system does not invent counterfactuals when no eligible rejected proposal exists." />}
      </div></section>

      <section className="section" id="leaderboard"><div className="content">
        <SectionHead eyebrow="EVIDENCE-WEIGHTED ALLOCATION" title="Agent leaderboard" copy="Scores shrink toward a neutral prior with sparse samples. Phase 1 performance is not attributed to these research agents." />
        {scores.length ? <div className="leaderboard">{scores.map((score, index) => <article key={score.agent}><span className="rank">0{index + 1}</span><div className="leader-name"><b>{score.agent}</b><small>{score.basis}</small></div><div className="leader-score"><strong>{score.score.toFixed(2)}</strong><Progress value={score.score} tone={index === 0 ? "green" : "cyan"} /></div><div><span>Shadow samples</span><b>{score.shadow_samples}</b></div><div><span>Shadow P&L</span><b>{money(score.shadow_pnl)}</b></div></article>)}</div> : <EmptyState title="No scored agents" copy="Leaderboard values appear only from recorded evidence." />}
      </div></section>

      <section className="section alternate" id="cycles"><div className="content">
        <SectionHead eyebrow="FINITE DRY-RUN DISPATCH" title="Autonomous cycles" copy="Recorded research cycles are idempotent and non-overlapping. Autonomous broker execution remains disabled." aside={<Pill tone="muted">{bundle.phase2?.batch_status.status?.toUpperCase() ?? "UNAVAILABLE"}</Pill>} />
        {bundle.phase2?.cycles.length ? <div className="cycles-table"><div className="table-head"><span>Cycle</span><span>Observed</span><span>Decision</span><span>Broker action</span></div>{bundle.phase2.cycles.map(item => <article key={item.id}><code>{item.id.slice(0, 8)}</code><span>{when(item.created_at)}</span><Pill tone="amber">{item.decision.replaceAll("_", " ")}</Pill><b>NONE</b></article>)}</div> : <EmptyState title="No cycle history" copy="No autonomous cycle values are synthesized." />}
      </div></section>

      <section className="section" id="audit"><div className="content">
        <SectionHead eyebrow="IMMUTABLE RESEARCH LEDGER" title="Research audit" copy="A replayable stage trail from underlying selection through risk, shadow research, and position review." aside={cycle ? <code className="cycle-id">{cycle.id.slice(0, 8)}</code> : null} />
        {cycle?.timeline.length ? <ol className="audit-timeline">{cycle.timeline.map(item => <li key={item.sequence}><i>{String(item.sequence + 1).padStart(2, "0")}</i><div><b>{item.stage.replaceAll("_", " ")}</b><span>{when(item.timestamp)}</span></div><em /></li>)}</ol> : <EmptyState title="No audit timeline" copy="Audit stages appear only from a persisted cycle." />}
      </div></section>

      <section className="section architecture-section quant-grid" id="architecture"><div className="content">
        <SectionHead eyebrow="BUILT TO FAIL CLOSED" title="Reliability architecture" copy="Execution is a separately authorized, durable transaction—not a side effect of agent output." />
        <div className="reliability-grid">{[["Cycle lease", "Single-flight coordination", "One active research cycle; stale locks expire safely."], ["Durable intent", "Persist before dispatch", "Every broker action is recorded before network contact."], ["Atomic claim", "One worker wins", "Database coordination prevents overlapping submission ownership."], ["Reconciliation", "Read before retry", "Unknown broker responses are queried by client order ID."], ["Bounded session", "Expiry plus budgets", "Opening, closing, and total order budgets are atomic."], ["Terminal shutdown", "Flags return false", "Completion, expiry, kill, or failure forces execution off."]].map(([name, principle, copy], index) => <article key={name}><span>0{index + 1}</span><b>{name}</b><small>{principle}</small><p>{copy}</p></article>)}</div>
        <div className="architecture-flow"><div><span>ALPACA DATA</span><b>Read-only state</b></div><i>→</i><div><span>AGENT ARENA</span><b>Structured theses</b></div><i>→</i><div><span>RISK</span><b>Final authority</b></div><i>→</i><div><span>INTENT + SESSION</span><b>Durable boundaries</b></div><i>→</i><div className="locked"><span>ALPACA PAPER</span><b>LOCKED</b></div></div>
        <div className="service-strip"><div><span className="status-dot" /><b>ALPACA PAPER</b><small>{bundle.phase1?.integrations.alpaca ? "CONNECTED" : "UNAVAILABLE"}</small></div><div><span className="status-dot" /><b>SUPABASE AUDIT</b><small>{bundle.phase1?.integrations.supabase && bundle.phase2?.database_connected ? "HEALTHY" : "UNAVAILABLE"}</small></div><div><span className="status-dot" /><b>RISK ENGINE</b><small>{bundle.phase1?.integrations.risk_engine ? "ACTIVE" : "UNAVAILABLE"}</small></div><div><span className="status-dot amber" /><b>EXECUTION</b><small>DISABLED</small></div><div><span className="status-dot red" /><b>LIVE TRADING</b><small>HARD BLOCKED</small></div></div>
      </div></section>
    </main>
    <footer className="site-footer"><div className="content"><div><span className="brand-footer">THESIS<b>CIRCUIT</b></span><p>AI strategies compete. Risk decides. Sometimes the best trade is no trade.</p></div><div className="footer-disclosure"><b>SIMULATED PAPER TRADING — NO REAL FUNDS</b><p>Results are hypothetical and are not investment advice. Options carry significant risk, and all investments involve risk.</p></div><div><b>PRODUCTION SAFETY</b><p>Execution disabled · Autonomous trading disabled · Live trading blocked</p></div></div></footer>
  </div>;
}
