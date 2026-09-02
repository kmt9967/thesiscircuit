"""Scan versioned and pending files without printing potential secret values."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "private-key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "github-token": r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})",
    "supabase-server-key": r"sb_secret_[A-Za-z0-9_-]{20,}",
    "jwt": r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}",
    "credential-assignment": r'''(?i)(?:api_secret|service_role_key|execution_token|password)[ \t]*[=:][ \t]*["']?[A-Za-z0-9_+/=-]{24,}''',
}


def main() -> None:
    names = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).decode().split("\0")
    violations = []
    for name in filter(None, names):
        path = ROOT / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in PATTERNS.items():
            if re.search(pattern, text):
                violations.append(f"{name}: {label}")
    if violations:
        raise SystemExit("Potential credentials found (values suppressed):\n" + "\n".join(violations))
    print("Tracked/pending secret scan passed; no credential patterns detected.")


if __name__ == "__main__":
    main()
