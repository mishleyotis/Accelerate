#!/usr/bin/env python3
"""Secret scan (Implementation Plan S.2) — pre-commit hook and CI step.

Fails if anything that looks like a credential is committed: private key
material, service-account JSON, cloud API keys, bearer tokens, or a
populated .env. With IAM database auth there is no DB password at all,
so any hit is a mistake by construction.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = [
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key material"),
    (re.compile(r'"type"\s*:\s*"service_account"'), "GCP service-account JSON"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "Google API key"),
    (re.compile(r"\bsk-ant-[0-9A-Za-z_-]{20,}\b"), "Anthropic API key"),
    (re.compile(r"\bsk-[0-9A-Za-z]{40,}\b"), "secret key token"),
    (re.compile(r"\bghp_[0-9A-Za-z]{36}\b"), "GitHub token"),
    (re.compile(r"\bxox[bapors]-[0-9A-Za-z-]{10,}\b"), "Slack token"),
    (re.compile(r"(?i)\b(password|passwd|secret|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"), "hardcoded credential assignment"),
]
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".woff", ".woff2", ".ico", ".gif", ".pdf"}
# The prototype and docs contain the words 'token'/'secret' in prose and
# mock data; only the high-confidence patterns apply there.
PROSE_DIRS = ("docs/", "prototype/")
HIGH_CONFIDENCE = {0, 1, 2, 3, 4, 5, 6}
# The legacy snapshot is frozen reference material, sanitised before import
# (see SNAPSHOT_README.md) — its tests carry deliberate FAKE key fixtures.
# Nothing new is ever added there, so it is excluded rather than allowlisted
# pattern-by-pattern.
EXCLUDED_DIRS = ("apps/dma-insights/",)


def staged_files():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    return [f for f in out if f]


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [f for f in out if f]


def main() -> int:
    files = staged_files() if "--staged" in sys.argv else tracked_files()
    hits = []
    for rel in files:
        if rel.startswith(EXCLUDED_DIRS):
            continue
        p = ROOT / rel
        if not p.is_file() or p.suffix.lower() in SKIP_SUFFIX:
            continue
        if rel.endswith(".env") or (".env." in rel and not rel.endswith(".env.example")):
            hits.append(f"{rel}: populated environment file committed")
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        prose = rel.startswith(PROSE_DIRS)
        for i, (rx, label) in enumerate(PATTERNS):
            if prose and i not in HIGH_CONFIDENCE:
                continue
            m = rx.search(text)
            if m:
                line = text.count("\n", 0, m.start()) + 1
                hits.append(f"{rel}:{line}: {label}")
    if hits:
        print("SECRET SCAN FAILED:")
        print("\n".join(hits))
        return 1
    print(f"Secret scan passed ({len(files)} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
