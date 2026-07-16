"""Walk the dma-insights tree and emit a 3-tier QA file ledger.

Per the original v2 QA plan §1.9 + the Batch 1 plan: every file in
the app's runtime + test + infra + doc surface gets a row in the
ledger. Tier A files (~200) get a full per-file QA card; Tier B
(~120) get a batch summary; Tier C (~400) get an inventory line.

Tier rules (deterministic; see _tier_for() below):

  Tier A — Runtime code that ships to prod:
    - apps/dma-insights/backend/app/**/*.py
    - apps/dma-insights/backend/workers/**/*.py
    - apps/dma-insights/backend/alembic/versions/*.py
    - apps/dma-insights/frontend/src/**/*.{ts,tsx}
    - apps/dma-insights/infra/*.sh
    - apps/dma-insights/infra/docker/*.Dockerfile

  Tier B — Tests, docs, infra config:
    - apps/dma-insights/backend/tests/**/*.py        (test files only)
    - apps/dma-insights/frontend/e2e/**/*.{ts,spec.ts}
    - apps/dma-insights/docs/**/*.md
    - apps/dma-insights/infra/terraform/*.tf
    - apps/dma-insights/infra/cloudbuild.yaml
    - apps/dma-insights/backend/pyproject.toml
    - apps/dma-insights/frontend/package.json

  Tier C — Fixtures, generated, reference (inventory-only):
    - apps/dma-insights/backend/tests/fixtures/**          (collapsed to one row per package root)
    - apps/dma-insights/docs/reference/**
    - apps/dma-insights/frontend/src/mock/**
    - everything else under the app subtree

Output: both .md (human read) and .json (machine consumable) at
docs/qa/qa_file_ledger.{md,json}. Each row has:
  tier, path, kind, size_bytes, line_count, sha256_8, tests_that_cover_it,
  references_to, last_modified.

`tests_that_cover_it` is a grep-based reverse-index: for each Tier
A file, find the tests that import or reference its module/symbol.
Best-effort; no claim of completeness — a missing entry is a
test-gap-finding for Batch 8.

Run:
  python -m app.scripts.ledger_walker
  python -m app.scripts.ledger_walker --output-md docs/qa/qa_file_ledger.md \\
                                       --output-json docs/qa/qa_file_ledger.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

TIER_A = "A"
TIER_B = "B"
TIER_C = "C"

REPO_APP_ROOT = Path(__file__).resolve().parents[3]  # apps/dma-insights/


@dataclass
class LedgerRow:
    tier: str
    path: str  # relative to REPO_APP_ROOT
    kind: str  # "router" / "service" / "parser" / "test" / "doc" / "fixture" / etc.
    size_bytes: int
    line_count: int
    sha256_8: str
    last_modified: str  # ISO date
    tests_that_cover_it: list[str] = field(default_factory=list)
    references_to: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tier": self.tier, "path": self.path, "kind": self.kind,
            "size_bytes": self.size_bytes, "line_count": self.line_count,
            "sha256_8": self.sha256_8, "last_modified": self.last_modified,
            "tests_that_cover_it": self.tests_that_cover_it,
            "references_to": self.references_to,
        }


_TIER_A_GLOBS = [
    "backend/app/**/*.py",
    "backend/workers/**/*.py",
    "backend/alembic/versions/*.py",
    "frontend/src/**/*.ts",
    "frontend/src/**/*.tsx",
    "infra/*.sh",
    "infra/docker/*.Dockerfile",
    "infra/docker/*.dockerfile",
]

_TIER_B_GLOBS = [
    "backend/tests/**/*.py",
    "frontend/e2e/**/*.ts",
    "frontend/e2e/**/*.spec.ts",
    "docs/**/*.md",
    "infra/terraform/*.tf",
    "infra/cloudbuild.yaml",
    "backend/pyproject.toml",
    "backend/alembic.ini",
    "frontend/package.json",
    "frontend/vite.config.ts",
    "frontend/vitest.config.ts",
    "frontend/playwright.config.ts",
    "frontend/tsconfig.json",
]


def _tier_for(rel_path: str) -> str | None:
    """Classify the file into A / B / C; None = skip (not part of the app)."""
    p = rel_path.replace("\\", "/")
    # Skip generated / venv / node_modules / __pycache__ / dist + the
    # walker's own output files (otherwise re-running the walker
    # produces a different output hash each time -- the previous run's
    # output participates in the new run's hash).
    for skip in (
        "__pycache__/", ".venv/", "node_modules/", "dist/",
        ".pytest_cache/", ".ruff_cache/", "build/", ".next/",
        ".git/", "venv/", ".terraform/", "dist-standalone/",
    ):
        if skip in p:
            return None
    if p in ("docs/qa/qa_file_ledger.md", "docs/qa/qa_file_ledger.json"):
        return None
    # Demo / wireframe-guide trees: stakeholder-demo only per ADR 0016.
    # Bucket as Tier C (inventory-only) so they're tracked but don't
    # contaminate Tier A code-coverage counts.
    if p.startswith(("frontend/standalone-src/", "frontend/_prototype/",
                     "docs/wireframe-2026-06/")):
        return TIER_C
    # Tier A allowlist
    for glob in _TIER_A_GLOBS:
        if _glob_match(p, glob):
            return TIER_A
    # Tier B allowlist
    for glob in _TIER_B_GLOBS:
        if _glob_match(p, glob):
            return TIER_B
    # Fixtures: collapsed elsewhere; reference docs: Tier C
    if p.startswith("backend/tests/fixtures/"):
        return None  # handled by the per-package collapser
    if p.startswith("docs/reference/"):
        return TIER_C
    if p.startswith("frontend/src/mock/"):
        return TIER_C
    # Static brand / public assets: Tier C inventory
    if p.startswith(("frontend/public/", "backend/static/")):
        return TIER_C
    # Anything else under the app subtree → Tier C catch-all
    if p.startswith(("backend/", "frontend/", "infra/", "docs/", "workers/")):
        return TIER_C
    return None


def _glob_match(path: str, glob: str) -> bool:
    """Translate a `**/*.ext` style glob to a regex match."""
    rx = re.escape(glob).replace(r"\*\*/", "(?:.*/)?").replace(r"\*", "[^/]*")
    return re.fullmatch(rx, path) is not None


def _kind_for(rel_path: str) -> str:
    # Lower-case + leading slash so substring checks ("/app/" etc.)
    # match the project-root-relative paths the walker emits
    # ("backend/app/routers/foo.py").
    p = "/" + rel_path.lower()
    # Backend buckets
    if "/app/routers/" in p:
        return "router"
    if "/app/services/parsers/" in p:
        return "parser"
    if "/app/services/" in p:
        return "service"
    if "/app/scripts/" in p:
        return "script"
    if "/app/schemas/" in p:
        return "schema"
    if "/app/models/" in p:
        return "model"
    if "/workers/" in p:
        return "worker"
    if "/alembic/versions/" in p:
        return "migration"
    if "/tests/" in p:
        return "test"
    if "/e2e/" in p:
        return "e2e"
    # Frontend buckets (check before generic docs)
    if "/frontend/src/components/" in p:
        return "component"
    if "/frontend/src/pages/" in p:
        return "page"
    if "/frontend/src/lib/" in p:
        return "frontend_lib"
    if "/frontend/src/hooks/" in p:
        return "frontend_hook"
    if "/frontend/src/store/" in p:
        return "frontend_store"
    if "/frontend/src/__tests__/" in p:
        return "frontend_test"
    if "/frontend/src/" in p and p.endswith((".ts", ".tsx")):
        return "frontend_src"
    # Demo / wireframe / prototype trees
    if "/standalone-src/" in p or "/_prototype/" in p \
            or "/wireframe-2026-06/" in p:
        return "demo"
    if "/mock/" in p:
        return "mock_data"
    if "/public/" in p or "/static/" in p:
        return "static_asset"
    # Generic
    if p.endswith(".md"):
        return "doc"
    if p.endswith(".sh"):
        return "infra_shell"
    if "dockerfile" in p:
        return "dockerfile"
    if p.endswith(".tf"):
        return "terraform"
    if "/reference/" in p:
        return "reference_doc"
    return "other"


def _hash8(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()[:8]


def _line_count(path: Path) -> int:
    try:
        return sum(1 for _ in path.open("rb"))
    except OSError:
        return 0


def _last_modified(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts).date().isoformat()
    except OSError:
        return ""


def _find_tests_covering(
    rel_path: str, test_files: list[Path]
) -> list[str]:
    """Best-effort: search test files for imports / mentions of the
    module derived from rel_path.
    """
    if not rel_path.startswith("backend/app/") and not rel_path.startswith(
        "backend/workers/"
    ):
        return []
    p = rel_path
    # backend/app/services/parsers/dma_package.py -> app.services.parsers.dma_package
    if p.startswith("backend/"):
        p = p[len("backend/") :]
    if p.endswith(".py"):
        p = p[:-3]
    module = p.replace("/", ".")
    leaf = module.rsplit(".", 1)[-1]
    hits: set[str] = set()
    # Single subprocess grep against the test files set: cheap and precise.
    try:
        r = subprocess.run(
            ["grep", "-l", "-E", f"{re.escape(module)}|from .*{re.escape(leaf)}",
             "--include=*.py", "-r",
             str(REPO_APP_ROOT / "backend" / "tests")],
            capture_output=True, text=True, timeout=20, check=False,
        )
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line:
                try:
                    rel = Path(line).resolve().relative_to(REPO_APP_ROOT).as_posix()
                    hits.add(rel)
                except ValueError:
                    pass
    except (subprocess.SubprocessError, OSError):
        pass
    return sorted(hits)


def _collapse_fixture_packages() -> list[LedgerRow]:
    """Collapse per-file fixture rows into one row per package root."""
    out: list[LedgerRow] = []
    fixt_root = REPO_APP_ROOT / "backend" / "tests" / "fixtures"
    if not fixt_root.exists():
        return out
    # dma_packages_sanitized: 5 directories at depth 1.
    for sub in ("dma_packages_sanitized", "dma_packages_batches"):
        base = fixt_root / sub
        if not base.exists():
            continue
        if sub == "dma_packages_sanitized":
            roots = [p for p in base.iterdir() if p.is_dir()]
        else:
            # dma_packages_batches: batch_NN / <Client> - DMA / ...
            roots = []
            for batch in sorted(base.iterdir()):
                if batch.is_dir() and batch.name.startswith("batch_"):
                    for pkg in sorted(batch.iterdir()):
                        if pkg.is_dir():
                            roots.append(pkg)
        for r in sorted(roots):
            try:
                total_bytes = sum(
                    f.stat().st_size for f in r.rglob("*") if f.is_file()
                )
                file_count = sum(1 for f in r.rglob("*") if f.is_file())
            except OSError:
                continue
            rel = r.resolve().relative_to(REPO_APP_ROOT).as_posix()
            out.append(LedgerRow(
                tier=TIER_C, path=rel, kind="fixture_package",
                size_bytes=total_bytes, line_count=file_count,
                sha256_8="", last_modified=_last_modified(r),
            ))
    return out


def walk_ledger() -> list[LedgerRow]:
    rows: list[LedgerRow] = []
    test_files: list[Path] = []
    for p in REPO_APP_ROOT.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel = p.resolve().relative_to(REPO_APP_ROOT).as_posix()
        except ValueError:
            continue
        tier = _tier_for(rel)
        if tier is None:
            continue
        size = p.stat().st_size
        rows.append(LedgerRow(
            tier=tier, path=rel, kind=_kind_for(rel),
            size_bytes=size, line_count=_line_count(p),
            sha256_8=_hash8(p), last_modified=_last_modified(p),
        ))
        if tier == TIER_B and "/tests/" in rel and rel.endswith(".py"):
            test_files.append(p)
    # Fixture packages — collapsed
    rows.extend(_collapse_fixture_packages())
    # Tier A: fill tests_that_cover_it.
    for r in rows:
        if r.tier == TIER_A and r.path.endswith(".py"):
            r.tests_that_cover_it = _find_tests_covering(r.path, test_files)
    return rows


def emit_markdown(rows: list[LedgerRow]) -> str:
    by_tier: dict[str, list[LedgerRow]] = {TIER_A: [], TIER_B: [], TIER_C: []}
    for r in rows:
        by_tier[r.tier].append(r)
    out = [
        "# DMA Insights — QA File Ledger (Batch 1)",
        "",
        "Auto-generated by `app/scripts/ledger_walker.py`. Re-run on every "
        "Batch-N gate to verify the file inventory stays in sync. Each tier "
        "rolls a different audit depth: A = per-file QA card, B = batch "
        "summary, C = inventory line.",
        "",
        f"**Totals:** Tier A = {len(by_tier[TIER_A])} files, "
        f"Tier B = {len(by_tier[TIER_B])} files, "
        f"Tier C = {len(by_tier[TIER_C])} files. "
        f"**Grand total: {sum(len(v) for v in by_tier.values())} rows.**",
        "",
    ]
    for tier, label in (
        (TIER_A, "Tier A — runtime code (per-file QA card)"),
        (TIER_B, "Tier B — tests / docs / infra config (batch summary)"),
        (TIER_C, "Tier C — fixtures / reference / mock (inventory)"),
    ):
        out.extend([
            f"## {label}",
            "",
            "| Path | Kind | LOC | Bytes | SHA256[:8] | Tests covering it | Last modified |",
            "|---|---|---:|---:|---|---|---|",
        ])
        sorted_rows = sorted(by_tier[tier], key=lambda r: r.path)
        for r in sorted_rows:
            tests = ", ".join(r.tests_that_cover_it[:3])
            if len(r.tests_that_cover_it) > 3:
                tests += f" (+{len(r.tests_that_cover_it) - 3} more)"
            tests = tests or "—"
            out.append(
                f"| `{r.path}` | {r.kind} | {r.line_count} | "
                f"{r.size_bytes} | `{r.sha256_8}` | {tests} | "
                f"{r.last_modified} |"
            )
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--output-md",
        default=str(REPO_APP_ROOT / "docs" / "qa" / "qa_file_ledger.md"),
    )
    ap.add_argument(
        "--output-json",
        default=str(REPO_APP_ROOT / "docs" / "qa" / "qa_file_ledger.json"),
    )
    args = ap.parse_args()
    rows = walk_ledger()
    out_md = Path(args.output_md)
    out_json = Path(args.output_json)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(emit_markdown(rows), encoding="utf-8")
    out_json.write_text(
        json.dumps([r.to_dict() for r in rows], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    counts = {TIER_A: 0, TIER_B: 0, TIER_C: 0}
    for r in rows:
        counts[r.tier] += 1
    print(
        f"# wrote {out_md} + {out_json}: "
        f"A={counts[TIER_A]}, B={counts[TIER_B]}, C={counts[TIER_C]}, "
        f"total={sum(counts.values())}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
