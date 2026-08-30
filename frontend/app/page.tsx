const gates = [
  ["Mode lock", "PAPER ONLY", "Alpaca paper endpoint is the only accepted broker URL."],
  ["Execution", "DISABLED", "Phase 0 contains no order submission endpoint or broker method."],
  ["Risk authority", "DETERMINISTIC", "Any failed gate vetoes a thesis; agents cannot override it."],
  ["Evidence", "REPLAYABLE", "Votes, vetoes, and decision events form an ordered audit trail."],
] as const;

const rules = [
  "Autonomous AI trading agent",
  "Alpaca Trading API with MCP or CLI",
  "Options incorporated in every strategy",
  "Fresh judging paper account · $100,000",
  "Public repo, live app, video, slides, one-page write-up",
] as const;

export default function Home() {
  return (
    <main>
      <nav aria-label="Primary">
        <a className="brand" href="#top">THESIS/CIRCUIT</a>
        <div><a href="#architecture">Circuit</a><a href="#rules">Rules</a><a href="#safety">Safety</a></div>
      </nav>

      <section className="hero" id="top">
        <div className="eyebrow"><span /> ALPACA PAPER ENVIRONMENT · PHASE 0</div>
        <h1>Every trade thesis<br />must survive the circuit.</h1>
        <p className="lede">A committee of AI agents researches defined-risk options ideas. A deterministic governor cross-examines every claim, vetoes unsafe proposals, and preserves the complete reasoning trail for replay.</p>
        <div className="heroActions"><a className="primary" href="#architecture">Inspect the circuit</a><span className="zero">TRADES PLACED <b>0</b></span></div>
      </section>

      <section className="status" id="safety" aria-label="Safety controls">
        {gates.map(([label, value, detail]) => <article key={label}><small>{label}</small><strong>{value}</strong><p>{detail}</p></article>)}
      </section>

      <section className="split" id="architecture">
        <div><div className="eyebrow"><span /> DECISION ARCHITECTURE</div><h2>Debate is probabilistic.<br />Risk is not.</h2><p>Market, options, risk, and skeptic agents submit typed votes. Consensus may advance a thesis to review. Only code-owned gates decide whether it is safe enough for paper research.</p></div>
        <ol className="circuit">
          <li><b>01</b><span><strong>Observe</strong><small>Market inputs become an immutable request.</small></span></li>
          <li><b>02</b><span><strong>Deliberate</strong><small>Independent agents expose confidence and rationale.</small></span></li>
          <li><b>03</b><span><strong>Govern</strong><small>Loss, freshness, expiry, and mode gates can veto.</small></span></li>
          <li><b>04</b><span><strong>Replay</strong><small>Every event is ordered for judge verification.</small></span></li>
        </ol>
      </section>

      <section className="rules" id="rules">
        <div><div className="eyebrow"><span /> OFFICIAL REQUIREMENTS</div><h2>Built around the rules,<br />not around assumptions.</h2></div>
        <ul>{rules.map((rule, index) => <li key={rule}><b>0{index + 1}</b>{rule}<span>✓</span></li>)}</ul>
      </section>

      <footer><p>Paper trading is hypothetical. No real funds. Not investment advice. Options and all investments involve risk.</p><span>THESISCIRCUIT / 2026</span></footer>
    </main>
  );
}

