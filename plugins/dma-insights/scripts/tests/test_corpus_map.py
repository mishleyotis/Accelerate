"""The corpus map covers every produced surface.

Owner goal, 2026-08-20: the survey must map everything — package sources,
storyline inputs and enrichment precedence per surface, not just evidence
plumbing. This test pins the coverage: any surface the census gives a
producing agent must have a row in 02-inputs/5-corpus-map.md, so a new
surface cannot ship without its source map.
"""
import re
from pathlib import Path

SKILL = (Path(__file__).resolve().parents[2]
         / "skills" / "dma-surface-production")
CENSUS = SKILL / "05-lifecycle" / "surface-map.md"
CORPUS_MAP = SKILL / "02-inputs" / "5-corpus-map.md"


def _produced_ids():
    ids = []
    in_page_census = False
    for line in CENSUS.read_text().splitlines():
        if line.startswith("## The page census"):
            in_page_census = True
            continue
        if in_page_census and line.startswith("## "):
            break
        m = re.match(r"\|\s*([A-Z]\d+b?)\s*\|", line)
        if not m or not in_page_census:
            continue
        cells = [c.strip() for c in line.split("|")]
        # producing agent is the 5th data column
        agent = cells[5] if len(cells) > 5 else ""
        if "server-computed" in agent or agent in ("", "—"):
            continue
        ids.append(m.group(1))
    return ids


def test_every_produced_surface_has_a_corpus_map_row():
    ids = _produced_ids()
    assert len(ids) >= 30, f"census parse degraded: {len(ids)} ids"
    body = CORPUS_MAP.read_text()
    missing = [i for i in ids if not re.search(rf"\b{re.escape(i)}\b", body)]
    assert not missing, f"surfaces with no corpus-map row: {missing}"


def test_the_map_carries_the_ladder_and_the_precedence_tiers():
    body = CORPUS_MAP.read_text()
    for required in ("resilience ladder", "P0", "P1", "P2", "P3",
                     "corpus_search", "package_map", "evidence_normalize",
                     "UNVERIFIED"):
        assert required in body, required
