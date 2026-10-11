"""Anti-gaming (brief §4): no client-specific string in engine code or tests.

The list is the display ids and names of every client the repository's
gold fixtures and decisions name. It lives HERE, in the test, so the engine
package itself never has to spell one. CI runs this file; a grep in the
engine's own Makefile target runs the same list.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = [ROOT / "evidence_engine", ROOT / "evidence_server.py", ROOT / "registry",
        ROOT / "eval" / "harness.py", ROOT / "tests"]
#: Client names appear in the repo's own fixtures and decisions; none may
#: appear in the engine. Lower-cased substring match on every text file.
FORBIDDEN = ("baxter", "bcu.org", "logix", "lfcu.com", "golden 1", "golden1",
             "swbc", "arbor bank", "first tech", "t. rowe", "troweprice",
             "ima financial", "interac", "frost bank", "fisher investments",
             "axos", "gulf coast", "goeasy", "odlum")
_TEXT = {".py", ".yaml", ".yml", ".json", ".md", ".txt", ".toml", ".cfg", ".ini"}


def _files():
    for base in SCAN:
        if base.is_file():
            yield base
            continue
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix in _TEXT and "__pycache__" not in p.parts:
                yield p


def test_no_client_specific_strings():
    hits = []
    me = Path(__file__).resolve()
    for p in _files():
        if p.resolve() == me:
            continue
        text = p.read_text(encoding="utf-8", errors="replace").lower()
        for needle in FORBIDDEN:
            if needle in text:
                hits.append(f"{p.relative_to(ROOT)}: {needle!r}")
    assert not hits, "client-specific strings in engine code:\n" + "\n".join(hits)


def test_the_forbidden_list_is_not_empty():
    assert len(FORBIDDEN) >= 10


def test_golden_set_lives_outside_the_scanned_tree():
    """The golden set (eval/golden/) legitimately names clients; it is
    excluded from SCAN by construction, and this pins that."""
    assert not any(str(p).endswith("eval/golden") for p in SCAN)
    assert re.fullmatch(r"harness\.py", (ROOT / "eval" / "harness.py").name)
