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
