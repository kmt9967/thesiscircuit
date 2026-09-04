import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";

const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
const command = readFileSync(new URL("../app/command-center.tsx", import.meta.url), "utf8");
const navigation = readFileSync(new URL("../app/navigation.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../app/command-center.css", import.meta.url), "utf8");
const globals = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

assert.match(page, /CommandCenter/);
assert.match(page, /command-center\.css/);

for (const required of [
  "SIMULATED PAPER TRADING — NO REAL FUNDS",
  "Results are hypothetical and are not investment advice",
  "PAPER ONLY",
  "EXECUTION DISABLED",
  "AUTONOMY DISABLED",
  "LIVE BLOCKED",
  "ACTUAL ALPACA PAPER RESULTS",
  "Market intelligence",
  "Market regime",
  "Strategy arena",
  "Decision council",
  "Position watch",
  "The original paper trade",
  "Risk engine",
  "Shadow desk",
  "Agent leaderboard",
  "Autonomous cycles",
  "Research audit",
  "Reliability architecture",
]) {
  assert.ok(command.includes(required), `Missing required production UI state: ${required}`);
}

for (const endpoint of ["/phase1/dashboard", "/phase2/dashboard", "/phase2/portfolio"]) {
  assert.ok(command.includes(endpoint), `Missing real backend integration: ${endpoint}`);
}
assert.match(command, /const apiBase = "\/backend"/);

assert.match(command, /Promise\.allSettled/);
assert.match(command, /No account value is invented/);
assert.match(command, /No reconciled Alpaca order/);
assert.match(command, /An absent risk decision never implies approval/);
assert.match(command, /NEVER SENT TO ALPACA/);
assert.doesNotMatch(command, /PHASE1_EXECUTION_TOKEN|PHASE2_EXECUTION_TOKEN|SUPABASE_SERVICE|method:\s*["']POST/);
assert.doesNotMatch(command, /mockData|100366\.94|mockAccountMetrics/);

for (const group of ["Overview", "Intelligence", "Strategy", "Positions", "Research"]) {
  assert.ok(navigation.includes(group), `Missing navigation group: ${group}`);
}
assert.match(navigation, /role="dialog"/);
assert.match(navigation, /aria-modal="true"/);
assert.match(navigation, /document\.body\.style\.overflow = "hidden"/);
assert.match(navigation, /event\.key === "Escape"/);
assert.match(styles, /100dvh/);
assert.match(styles, /@media\(max-width:900px\)/);
assert.match(globals, /@media \(prefers-reduced-motion: reduce\)/);

console.log("Final UI port safety, real-data, navigation, responsive, and disclosure checks passed.");
