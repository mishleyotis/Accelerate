"""v2 QA — parser-robustness audit against a directory of real DMA packages.

Reproducible harness for the 2026-06-07 validation: 5 uploaded DMA
batches (34 real client packages) run through `parse_package` to surface
parser gaps the 5-folder reference sample didn't.

The batches are committed under
`tests/fixtures/dma_packages_batches/batch_0{1..5}/` (per maintainer
decision 2026-06-07 — see `docs/qa/qa_34package_validation.md`). Run
with no args to audit the committed corpus, or pass a path to audit a
different extraction:

    python qa_v2_34package_audit.py                 # committed corpus
    python qa_v2_34package_audit.py /path/to/batches # custom dir

Output: one row per detected client package with parse status + counts,
then a summary.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from app.services.parsers.dma_package import parse_package

# Committed corpus location (relative to this script).
DEFAULT_CORPUS = (
    Path(__file__).parent
    / "tests" / "fixtures" / "dma_packages_batches"
)

CANON = re.compile(
    r"^(01_evidence|02_research|03_scoring|04_report|05_|06_peers"
    r"|07_governance|08_appendic)"
)


def find_root(client: Path) -> Path:
    """Find the dir containing canonical numbered subfolders, or the
    client dir itself (partial / non-canonical packages)."""
    candidates = [client] + [p for p in client.rglob("*") if p.is_dir()]
    for sub in candidates:
        try:
            kids = {x.name for x in sub.iterdir() if x.is_dir()}
        except OSError:
            continue
        if any(CANON.match(k) for k in kids):
            return sub
    return client


def audit_dir(base: Path) -> list[tuple[str, str, dict]]:
    results: list[tuple[str, str, dict]] = []
    for batch in sorted(base.iterdir()):
        if not batch.is_dir():
            continue
        for client in sorted(batch.iterdir()):
            if not client.is_dir():
                continue
            root = find_root(client)
            name = client.name.replace(" - DMA", "")
            try:
                pkg = parse_package(root)
                rm = pkg.run_manifest
                results.append((name, "OK", {
                    "inst": (rm.institution_name if rm else "")[:26],
                    "ev": len(pkg.evidence),
                    "sub": len(pkg.subcap_scores),
                    "rec": len(pkg.recommendations),
                    "sec": len(pkg.report_sections),
                    "lead": (
                        len(pkg.firmographics.leadership)
                        if pkg.firmographics else 0
                    ),
                    "warn": len(pkg.parser_warnings),
                }))
            except Exception as e:
                results.append((name, "FAIL", {
                    "err": f"{type(e).__name__}: {e}"[:90],
                }))
    return results


def main() -> int:
    base = Path(sys.argv[1]) if len(sys.argv) >= 2 else DEFAULT_CORPUS
    if not base.is_dir():
        print(f"not a directory: {base}")
        print(__doc__)
        return 2
    results = audit_dir(base)
    hdr = (
        f'{"Client":<42} {"St":<5} {"inst":<26} '
        f'{"ev":>4} {"sub":>4} {"rec":>4} {"sec":>4} {"led":>4} {"wn":>3}'
    )
    print(hdr)
    print("-" * len(hdr))
    ok = fail = 0
    for name, st, d in results:
        if st == "OK":
            ok += 1
            print(
                f'{name:<42} {st:<5} {d["inst"]:<26} '
                f'{d["ev"]:>4} {d["sub"]:>4} {d["rec"]:>4} '
                f'{d["sec"]:>4} {d["lead"]:>4} {d["warn"]:>3}'
            )
        else:
            fail += 1
            print(f'{name:<42} {st:<5} {d["err"]}')
    print("-" * len(hdr))
    print(f"TOTAL: {ok} OK, {fail} FAIL out of {len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
