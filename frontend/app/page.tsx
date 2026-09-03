import Dashboard from "./phase1-dashboard";
import Phase2Dashboard from "./phase2-dashboard";
import "./phase2.css";

export default function Home() {
  return (
    <main>
      <nav aria-label="Primary">
        <a className="brand" href="#top">THESIS/CIRCUIT</a>
        <div><a href="#arena">Arena</a><a href="#council">Council</a><a href="#shadows">Shadows</a><a href="#account">Paper account</a></div>
      </nav>
      <section className="hero compact" id="top">
        <div className="eyebrow"><span /> ALPACA PAPER ENVIRONMENT · PHASE 2 / DRY RUN</div>
        <h1>Competing theses.<br />Accountable decisions.</h1>
        <p className="lede">Three options strategies challenge the same market. A critic questions each thesis. Deterministic risk gets the final veto. Even the ideas we reject leave evidence.</p>
      </section>
      <Phase2Dashboard />
      <section className="panel"><small>PHASE 1 / PRESERVED EXECUTION EVIDENCE</small><h2>The original paper trade.</h2><p>One historical opening order. No additional opening or closing orders are authorized in Phase 2 Part 1.</p></section>
      <Dashboard />
      <footer>
        <p><strong>SIMULATED PAPER TRADING — NO REAL FUNDS.</strong> Results are hypothetical and are not investment advice.</p>
        <span>THESISCIRCUIT / 2026</span>
      </footer>
    </main>
  );
}
