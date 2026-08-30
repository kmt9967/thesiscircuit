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

console.log("Phase 1 frontend safety and empty-state checks passed.");
