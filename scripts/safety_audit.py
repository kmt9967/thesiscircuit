from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ("https://api.alpaca.markets", "submit_order(", "place_order(", "LIVE_TRADING_ALLOWED=true")
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
    print("Safety audit passed: paper-only configuration and no order-placement markers found.")


if __name__ == "__main__":
    main()
