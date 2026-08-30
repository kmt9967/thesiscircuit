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
    print("Safety audit passed: paper-only endpoints and one-shot order boundary verified.")


if __name__ == "__main__":
    main()
