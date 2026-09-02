"use client";

import { useEffect, useState } from "react";

type Option = {symbol: string; bid: number; ask: number; source: string; quote_at: string; theta: number | null; delta: number | null; gamma: number | null; vega: number | null; expiry: string};
type Proposal = {id: string; agent: string; thesis: string; confidence: number; estimated_max_loss: number; status: string; contract: Option | null; reasons_not_to_trade: string[]};
type Critic = {proposal_id: string; strongest_counterargument: string; concentration_risk: string; no_trade_argument: string};
type Risk = {proposal_id: string; decision: string; reasons: string[]; checks: {name: string; passed: boolean; reason: string}[]};
type Score = {agent: string; score: number; shadow_samples: number; shadow_pnl: number | null; executed_realized_pnl: number | null; basis: string};
type Shadow = {id: string; agent: string; symbol: string; timestamp: string; entry_reference: number; rejection_reason: string; hypothetical_max_loss: number};
type Mark = {shadow_id: string; timestamp: string; hypothetical_pnl: number; decision_regret: number; rejection_effect: string; horizon_complete: boolean};
type PositionReview = {timestamp: string; recommendation: string; reasons: string[]; hours_to_expiry: number | null; theta_daily_dollars: number | null; quote: Option | null; position: {symbol: string; qty: number; entry: number; current_price: number; market_value: number; unrealized_pl: number; unrealized_plpc: number}};
type Cycle = {id: string; created_at: string; decision: string; regime: {name: string; confidence: number; metrics: Record<string, number | null>}; proposals: Proposal[]; critics: Critic[]; risk: Risk[]; scores: Score[]; allocation: {decision: string; reason: string; proposal_id: string | null}; position_reviews: PositionReview[]; state: {data_errors: string[]}; timeline: {sequence: number; stage: string; timestamp: string}[]};
type Data = {latest: Cycle | null; execution_enabled: false; batch_status: {status: string}; shadows: Shadow[]; marks: Mark[]; cycles: {id: string; created_at: string; decision: string}[]};
type Portfolio = {observed_at: string; market_open: boolean; account: {equity: number; cash: number; buying_power: number; competition_pnl: number}; total_orders: number; positions: (PositionReview & {quote_fresh: boolean; mark_basis: string})[]};
const money = (n: number | null | undefined) => n == null ? "Not measured" : new Intl.NumberFormat("en-US", {style: "currency", currency: "USD"}).format(n);
const when = (t: string) => new Date(t).toLocaleString();

export default function Phase2Dashboard() {
  const [data, setData] = useState<Data | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [error, setError] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let mounted = true;
    const timeout = setTimeout(() => controller.abort(), 15000);
    fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/phase2/portfolio`, {cache: "no-store", signal: controller.signal})
      .then(r => {if (!r.ok) throw new Error("Broker unavailable"); return r.json();})
      .then(p => {if (mounted) setPortfolio(p);})
      .catch(() => {if (mounted) setPortfolio(null);});
    fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/phase2/dashboard`, {cache: "no-store", signal: controller.signal})
      .then(r => { if (!r.ok) throw new Error("Audit unavailable"); return r.json(); })
      .then(d => {if (mounted) {setData(d); setError(false);}})
      .catch(() => {if (mounted) setError(true);})
      ;
    return () => {mounted = false; clearTimeout(timeout); controller.abort();};
  }, [refresh]);
  const cycle = data?.latest;
  return <>
    <div className="disclosure">SIMULATED PAPER TRADING — NO REAL FUNDS</div>
    <section className="panel" id="actual-results"><small>ACTUAL ALPACA PAPER RESULTS</small><h2>Competition account.</h2>
      {portfolio ? <><div className="metrics"><article><small>Official account equity</small><strong>{money(portfolio.account.equity)}</strong></article><article><small>Competition P&amp;L vs $100,000</small><strong>{money(portfolio.account.competition_pnl)}</strong></article><article><small>Cash / options buying power</small><strong>{money(portfolio.account.cash)}</strong><small>{money(portfolio.account.buying_power)}</small></article></div><p>Broker read {when(portfolio.observed_at)} · Market {portfolio.market_open ? "OPEN" : "CLOSED"} · {portfolio.total_orders} historical orders. Not shadow returns or an official judging certification.</p>
      {portfolio.positions.map(r => <article className="agent-card" key={r.position.symbol}><h3>{r.position.symbol} · {r.position.qty} long</h3><p>Entry {money(r.position.entry)} · broker value {money(r.position.market_value)} · unrealized {money(r.position.unrealized_pl)}</p><p>{r.quote ? `Last available ${r.quote.source} bid / ask: ${money(r.quote.bid)} / ${money(r.quote.ask)} · ${when(r.quote.quote_at)}` : "Option quote unavailable"}. {r.quote_fresh ? "Fresh quote" : "STALE / not eligible for execution"}</p><p>Expiry {r.quote?.expiry ?? "Unknown"} · {r.hours_to_expiry?.toFixed(1) ?? "Unknown"} hours remaining at read time</p><p>Delta {r.quote?.delta ?? "Unknown"} · gamma {r.quote?.gamma ?? "Unknown"} · theta {r.quote?.theta ?? "Unknown"} · vega {r.quote?.vega ?? "Unknown"} — snapshot estimates, not live Greeks.</p><p><strong>{r.recommendation}</strong> · {r.reasons.join("; ")}</p><small>{r.mark_basis}. No closing authority; regime thesis unassessed until a fresh research cycle.</small></article>)}
      {!portfolio.positions.length && <p>No open paper position.</p>}</> : <p>Current broker account unavailable or loading. No account values are invented.</p>}
      <p>EXECUTION DISABLED · AUTONOMOUS TRADING DISABLED</p><p>Risk: min($500, 0.5% equity) per entry · 2% aggregate premium · 1% daily drawdown veto · 3 positions · one thesis per underlying · 15-minute cooldown.</p>
    </section>
    <section className="panel" id="arena">
      <header><div><small>PHASE 2 / READ-ONLY RESEARCH</small><h2>Strategy arena.</h2></div><span className="badge paper">EXECUTION DISABLED</span></header>
      <p>Three competing theses. One independent veto. No Phase 2 orders.</p>
      <button className="refresh" onClick={() => setRefresh(x => x + 1)}>Refresh recorded state</button>
      <p className="asof">{cycle ? `Recorded ${when(cycle.created_at)} · Finite batch ${data?.batch_status.status}` : "No completed Phase 2 cycle yet."} This is a timestamped snapshot, not a live price stream.</p>
      {error && <p role="alert">Audit unavailable. No execution is possible; previously loaded data may be stale.</p>}
      {!data && !error && <p role="status">Loading recorded research…</p>}
      {cycle && <div className="arena-grid">{cycle.proposals.map(p => {
        const score = cycle.scores.find(s => s.agent === p.agent);
        return <article className="agent-card" key={p.id}><small>{p.agent} AGENT</small><h3>{p.status.replaceAll("_", " ")}</h3><p>{p.thesis}</p><dl>
          <dt>Confidence</dt><dd>{(p.confidence * 100).toFixed(0)}% · heuristic, not probability</dd>
          <dt>Proposed risk</dt><dd>{money(p.estimated_max_loss)}</dd>
          <dt>Allocated capital</dt><dd>$0.00 · dry run only</dd>
          <dt>Executed P&amp;L</dt><dd>{money(score?.executed_realized_pnl)} · Phase 1 is not attributed to this agent</dd>
          <dt>Shadow P&amp;L</dt><dd>{money(score?.shadow_pnl)}</dd>
          <dt>Score</dt><dd>{score?.score ?? "Unavailable"}/100 · {score?.shadow_samples ?? 0} completed shadow horizons</dd>
        </dl></article>;
      })}</div>}
    </section>
    {cycle && <>
      <section className="panel" id="regime"><small>DETERMINISTIC MARKET FEATURES</small><h2>{cycle.regime.name.replaceAll("_", " ")}</h2><p>{(cycle.regime.confidence * 100).toFixed(0)}% heuristic confidence · IEX minute bars / source-labelled options</p><div className="metrics">{Object.entries(cycle.regime.metrics).map(([key, value]) => <article key={key}><small>{key.replaceAll("_", " ")}</small><strong>{value == null ? "Unavailable" : value.toFixed(4)}</strong></article>)}</div>{cycle.state.data_errors.map(e => <p key={e} className="asof">{e}</p>)}</section>
      <section className="panel" id="council"><small>META ALLOCATOR + HARD RISK OFFICER</small><h2>Decision council.</h2><span className="badge">{cycle.decision}</span><p>{cycle.allocation.reason}</p><div className="arena-grid">{cycle.proposals.map(p => {
        const critic = cycle.critics.find(c => c.proposal_id === p.id);
        const risk = cycle.risk.find(r => r.proposal_id === p.id);
        return <article className="agent-card" key={p.id}><small>{p.agent}</small><h3>{p.contract?.symbol ?? "NO TRADE"}</h3><p>{p.thesis}</p><p><strong>Critic:</strong> {critic?.strongest_counterargument}</p><p>{critic?.concentration_risk}</p><p><strong>Risk:</strong> {risk?.decision} · {risk?.checks.filter(g => g.passed).length}/{risk?.checks.length} gates</p><details><summary>Inspect risk reasons</summary><ul>{risk?.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></details><p>{cycle.allocation.proposal_id === p.id ? "Selected for research only" : "Not selected"}</p></article>;
      })}</div></section>
      <section className="panel" id="shadows"><small>COUNTERFACTUAL / NEVER SENT TO ALPACA</small><h2>Shadow desk.</h2><p>Hypothetical ask entry → later bid mark, without fees or fill guarantees. No simulated outcome is an Alpaca execution.</p>
        {!data?.shadows.length ? <p className="empty">No eligible rejected proposal has a shadow record yet.</p> : <div className="table-wrap"><table><thead><tr><th>Agent / contract</th><th>Entry / risk</th><th>Why rejected</th><th>Hypothetical outcome</th><th>Regret</th></tr></thead><tbody>{data.shadows.map(s => {
          const mark = data.marks.find(m => m.shadow_id === s.id);
          return <tr key={s.id}><td>{s.agent}<br/>{s.symbol}<small>{when(s.timestamp)}</small></td><td>{money(s.entry_reference)}<br/>{money(s.hypothetical_max_loss)}</td><td>{s.rejection_reason}</td><td>{money(mark?.hypothetical_pnl)}<small>{mark ? `${mark.rejection_effect} · ${mark.horizon_complete ? "horizon complete" : "interim, unscored"} · ${when(mark.timestamp)}` : "Awaiting later fresh quote"}</small></td><td>{money(mark?.decision_regret)}</td></tr>;
        })}</tbody></table></div>}
      </section>
      <section className="panel" id="position-manager"><small>REAL ALPACA PAPER POSITIONS / RECOMMENDATIONS ONLY</small><h2>Position watch.</h2>{cycle.position_reviews.map(r => <article className="agent-card" key={r.position.symbol}><span className="badge paper">{r.recommendation} · NOT EXECUTED</span><h3>{r.position.symbol}</h3><dl><dt>Quantity / entry</dt><dd>{r.position.qty} / {money(r.position.entry)}</dd><dt>Value / unrealized P&amp;L</dt><dd>{money(r.position.market_value)} / {money(r.position.unrealized_pl)} ({(r.position.unrealized_plpc * 100).toFixed(2)}%)</dd><dt>Quote / as of</dt><dd>{r.quote ? `${money(r.quote.bid)} / ${money(r.quote.ask)} · ${when(r.quote.quote_at)}` : "Fresh option quote unavailable"}</dd><dt>Expiry / time left</dt><dd>{r.quote?.expiry ?? "Unknown"} / {r.hours_to_expiry?.toFixed(1) ?? "Unknown"} hours</dd><dt>Theta / day</dt><dd>{money(r.theta_daily_dollars)} · model estimate</dd></dl><p>{r.reasons.join("; ")}</p><small>Broker snapshot {when(r.timestamp)}. No closing order is authorized.</small></article>)}</section>
      <section className="panel" id="research-audit"><small>IMMUTABLE CYCLE {cycle.id.slice(0, 8)}</small><h2>Research audit.</h2><ol className="timeline">{cycle.timeline.map(t => <li key={t.sequence}><b>{String(t.sequence + 1).padStart(2, "0")}</b><span>{t.stage.replaceAll("_", " ")}<small>{when(t.timestamp)}</small></span></li>)}</ol><p>{data?.cycles.length} recent recorded cycles. Agent scores cannot change hard risk limits.</p></section>
    </>}
  </>;
}
