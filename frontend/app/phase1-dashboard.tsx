"use client";

import { useEffect, useState } from "react";

type Account = { cash: number; buying_power: number; portfolio_value: number; equity: number };
type State = {
  generated_at: string; paper: true; execution_enabled: boolean; account: Account | null;
  integrations: Record<string, boolean>; latest_proposal: Record<string, unknown> | null;
  latest_risk: Record<string, unknown> | null; latest_order: Record<string, unknown> | null;
  latest_fill: Record<string, unknown> | null; latest_position: Record<string, unknown> | null;
  timeline: Array<Record<string, unknown>>;
};

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const money = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? `$${value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : "—";
const text = (value: unknown) => typeof value === "string" && value ? value : "—";
const short = (value: unknown) => typeof value === "string" ? `${value.slice(0, 8)}…${value.slice(-4)}` : "—";

export default function Dashboard() {
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiBase}/phase1/dashboard`, { signal: controller.signal, cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Backend returned ${response.status}`);
        return response.json() as Promise<State>;
      })
      .then(setState)
      .catch((reason: unknown) => {
        if (reason instanceof Error && reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, []);

  if (error) return <section className="empty"><strong>Live state unavailable</strong><p>{error}</p></section>;
  if (!state) return <section className="empty"><strong>Loading verified paper state…</strong></section>;

  const proposal = state.latest_proposal;
  const risk = state.latest_risk;
  const order = state.latest_order;
  const fill = state.latest_fill;
  const positionRecord = state.latest_position;
  const position = positionRecord && typeof positionRecord.position === "object" && positionRecord.position
    ? positionRecord.position as Record<string, unknown> : null;

  return <>
    <section className="disclosure">SIMULATED PAPER TRADING — NO REAL FUNDS</section>
    <section className="panel" id="account">
      <header><div><small>ACCOUNT</small><h2>Competition account</h2></div><span className="badge paper">PAPER TRADING</span></header>
      <div className="metrics">
        <article><small>Portfolio value</small><strong>{money(state.account?.portfolio_value)}</strong></article>
        <article><small>Cash</small><strong>{money(state.account?.cash)}</strong></article>
        <article><small>Buying power</small><strong>{money(state.account?.buying_power)}</strong></article>
        <article><small>Execution</small><strong className={state.execution_enabled ? "danger" : "safe"}>{state.execution_enabled ? "ENABLED" : "DISABLED"}</strong></article>
      </div>
    </section>
    <section className="panel">
      <header><div><small>SYSTEM STATUS</small><h2>Fail-closed services</h2></div></header>
      <div className="statusGrid">
        {[["Alpaca", state.integrations.alpaca], ["Supabase / database", state.integrations.supabase], ["Risk engine", state.integrations.risk_engine], ["Execution gate", state.execution_enabled]].map(([label, ok]) => <article key={String(label)}><span className={ok ? "dot on" : "dot"} /><strong>{label}</strong><small>{label === "Execution gate" ? (ok ? "ENABLED" : "DISABLED") : (ok ? "CONNECTED" : "UNAVAILABLE")}</small></article>)}
      </div>
    </section>
    <section className="twoCol" id="decision">
      <article className="panel card"><small>LATEST DECISION</small>{proposal ? <><h3>{text(proposal.instrument)}</h3><dl><dt>Strategy</dt><dd>{text(proposal.strategy_type)}</dd><dt>Rationale</dt><dd>{text(proposal.rationale)}</dd><dt>Risk</dt><dd>{text(risk?.decision)}</dd><dt>Timestamp</dt><dd>{text(proposal.created_at)}</dd></dl></> : <div className="empty inner"><strong>No executed proposal</strong><p>The official trading window has not opened. Nothing is represented as real.</p></div>}</article>
      <article className="panel card"><small>ORDER</small><span className="badge paper">PAPER</span>{order ? <><h3>{text(order.status).toUpperCase()}</h3><dl><dt>Instrument</dt><dd>{text(order.instrument)}</dd><dt>Quantity</dt><dd>{String(order.quantity ?? "—")}</dd><dt>Fill price</dt><dd>{money(fill?.price ?? order.filled_average_price)}</dd><dt>Reference</dt><dd>{short(order.alpaca_order_id)}</dd></dl></> : <div className="empty inner"><strong>No Alpaca order</strong><p>Zero opening orders have been submitted in Phase 1.</p></div>}</article>
    </section>
    <section className="panel card"><small>POSITION</small>{position ? <dl className="position"><dt>Instrument</dt><dd>{text(position.symbol)}</dd><dt>Quantity</dt><dd>{String(position.qty ?? "—")}</dd><dt>Entry</dt><dd>{money(Number(position.avg_entry_price))}</dd><dt>Current value</dt><dd>{money(Number(position.market_value))}</dd><dt>Unrealized P&amp;L</dt><dd>{money(Number(position.unrealized_pl))}</dd></dl> : <div className="empty inner"><strong>No paper position</strong><p>A real Alpaca-reported position will appear here after the authorized order fills.</p></div>}</section>
    <section className="panel" id="audit"><header><div><small>AUDIT TIMELINE</small><h2>Decision replay</h2></div></header>{state.timeline.length ? <ol className="timeline">{state.timeline.map((event, index) => <li key={String(event.id ?? index)}><b>{String(index + 1).padStart(2, "0")}</b><span><strong>{text(event.kind).replaceAll("_", " ")}</strong><small>{text(event.created_at)}</small></span></li>)}</ol> : <div className="empty inner"><strong>No execution events yet</strong><p>Proposal → Risk Approved → Paper Order Submitted → Actual Alpaca State will populate only from verified records.</p></div>}</section>
  </>;
}
