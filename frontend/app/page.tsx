import Dashboard from "./phase1-dashboard";

export default function Home() {
  return (
    <main>
      <nav aria-label="Primary">
        <a className="brand" href="#top">THESIS/CIRCUIT</a>
        <div><a href="#account">Account</a><a href="#decision">Decision</a><a href="#audit">Audit</a></div>
      </nav>
      <section className="hero compact" id="top">
        <div className="eyebrow"><span /> ALPACA PAPER ENVIRONMENT · PHASE 1</div>
        <h1>One trade.<br />Every reason visible.</h1>
        <p className="lede">A controlled options execution proof with deterministic market selection, code-owned risk gates, Alpaca-reported state, and a replayable server-side audit trail.</p>
      </section>
      <Dashboard />
      <footer>
        <p><strong>SIMULATED PAPER TRADING — NO REAL FUNDS.</strong> Results are hypothetical and are not investment advice.</p>
        <span>THESISCIRCUIT / 2026</span>
      </footer>
    </main>
  );
}
