import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";

const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
const dashboard = readFileSync(new URL("../app/phase1-dashboard.tsx", import.meta.url), "utf8");

assert.match(page, /SIMULATED PAPER TRADING — NO REAL FUNDS/);
assert.match(page, /not investment advice/);
assert.match(dashboard, /execution_enabled \? "ENABLED" : "DISABLED"/);
assert.match(dashboard, /No Alpaca order/);
assert.match(dashboard, /No paper position/);
assert.match(dashboard, /No executed proposal/);
assert.match(dashboard, /Readiness approval is not an executed trade/);
assert.doesNotMatch(dashboard, /The official trading window has not opened/);
assert.doesNotMatch(dashboard, /Zero opening orders have been submitted/);
assert.match(dashboard, /Reconciled position snapshot at/);
assert.match(dashboard, /Account read at/);
assert.match(dashboard, /eventTime\(event\)/);

console.log("Phase 1 frontend safety and empty-state checks passed.");

const research = readFileSync(new URL("../app/phase2-dashboard.tsx", import.meta.url), "utf8");
for (const required of ["COUNTERFACTUAL", "EXECUTION DISABLED", "Strategy arena", "Decision council", "Shadow desk", "Position watch", "NO TRADE", "Not measured", "No completed Phase 2 cycle", "not a live price stream", "NOT EXECUTED", "interim, unscored"]) {
  assert.ok(research.includes(required), `Missing Phase 2 disclosure/state: ${required}`);
}
assert.doesNotMatch(research, /PHASE1_EXECUTION_TOKEN|PHASE2_EXECUTION_TOKEN|SUPABASE_SERVICE|method:\s*["']POST/);
assert.match(research, /phase2\/dashboard/);
assert.match(research, /AbortController/);
assert.match(page, /Phase2Dashboard/);
console.log("Phase 2 research, counterfactual, missing-data and no-execution UI checks passed.");
for (const label of ["ACTUAL ALPACA PAPER RESULTS", "Competition P&", "AUTONOMOUS TRADING DISABLED",
  "STALE / not eligible for execution", "phase2/portfolio", "No account values are invented"]) {
  assert.ok(research.includes(label), `Missing Part 2 state: ${label}`);
}
