from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    "https://api.alpaca.markets",
    "LIVE_TRADING_ALLOWED=true",
    "ALLOW_LIVE_TRADING=true",
    "TRADING_MODE=live",
    "ALPACA_PAPER_TRADE=false",
)
SKIP_PARTS = {".git", ".venv", ".pytest_cache", "node_modules", ".next", ".tmp"}


def main() -> None:
    violations: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for needle in FORBIDDEN:
            if needle in text and path.name != "safety_audit.py":
                violations.append(f"{path.relative_to(ROOT)} contains forbidden marker {needle!r}")
    if violations:
        raise SystemExit("\n".join(violations))
    order_client = ROOT / "backend" / "app" / "services" / "alpaca.py"
    source = order_client.read_text(encoding="utf-8")
    if source.count("self.client.post(") != 1:
        raise SystemExit("Expected exactly one Alpaca order-submission path")
    if ".delete(" in source or "cancel_all" in source or "close_position" in source:
        raise SystemExit("Automatic cancel/close behavior is forbidden")
    sdk = (ROOT / "backend/app/services/alpaca_sdk.py").read_text(encoding="utf-8")
    if (sdk.count("self.trade.submit_order(") != 1 or "client._retry=0" not in sdk
            or "allow_redirects=False" not in sdk or "class GuardedSession" not in sdk):
        raise SystemExit("Official SDK must retain one guarded, no-retry PAPER submission boundary")
    print("Safety audit passed: paper-only endpoints and one-shot order boundary verified.")
    for path in (ROOT / "backend" / "app" / "phase2").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        if any(marker in source for marker in ("OrderService", "submit_order", "close_position", "cancel_order")):
            raise SystemExit(f"Phase 2 has forbidden broker write capability: {path.name}")
        if "/v2/orders\"" in source and path.name != "order_dispatch.py":
            raise SystemExit(f"Unexpected Phase 2 broker submission path: {path.name}")
    dispatch = (ROOT / "backend/app/phase2/order_dispatch.py").read_text(encoding="utf-8")
    if dispatch.count("self.broker.client.post(") != 1 or "await self.session_gate.submit(" not in dispatch:
        raise SystemExit("Expected one durable Phase 2 submission boundary")
    session_gate = (ROOT / "backend/app/phase2/execution_sessions.py").read_text(encoding="utf-8")
    session_sql = (ROOT / "database/migrations/006_phase2_execution_sessions.sql").read_text(encoding="utf-8")
    if ('"SUBMIT",preflight' not in session_gate or
        "phase2_advance_order_intent(intent_id,worker,'SUBMITTING'" not in session_sql):
        raise SystemExit("Session budget and irreversible submit transition must share one DB transaction")
    for name in ("engine.py", "data.py", "order_dry_run.py", "session_dry_run.py", "session_budget_dry_run.py", "outcomes.py"):
        source = (ROOT / "backend/app/phase2" / name).read_text(encoding="utf-8")
        if "PaperOrderDispatcher" in source or "order_dispatch import" in source:
            raise SystemExit(f"Dry-run/advisory code imported broker capability: {name}")
    api = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    if "PHASE1_RETIRED = True" not in api:
        raise SystemExit("Phase 1 authorization must remain permanently retired")
    if '@app.post("/phase2' in api:
        raise SystemExit("Phase 2 activation must not be frontend/API controlled")
    activation = (ROOT / "backend/app/phase2/activation.py").read_text(encoding="utf-8")
    if (activation.count('"EXECUTION_ENABLED": "false"') != 1
            or activation.count('"AUTONOMOUS_TRADING_ENABLED": "false"') != 1
            or '"replace": False' not in activation or "force_disabled" not in activation):
        raise SystemExit("Railway shutdown controller must only force both execution flags false")
    print("Phase 2 capability audit passed: bounded server-only activation, verified shutdown, Phase 1 retired.")


if __name__ == "__main__":
    main()
