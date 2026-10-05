"""A field the page prose names is a field the machine contract states.

RC-09 (SWBC gold audit, 2026-10-04; MEM-0084 RULE_HELD_IN_TWO_PLACES_DRIFTS).
The gates read `contracts_data.json`; the producer reads the 03-pages prose.
Where the prose named a field the contract did not, the field was optional in
practice — "payload shapes are law", and a shape absent from the law is not
one. Measured: `peer_synthesis` and `estate_reach` appeared 0 times in the
contract, `peer_deployments` twice, and C4's tile `state` only in C4.md; SWBC
promoted platform tiles without them and two context tiles with no state.

Two checks:
  1. every field path in a surface's "Information sources" table resolves in
     that surface's contract (field name, item key, item_shape key, or the
     contract's own doc text). The pre-existing naming drift is pinned in
     KNOWN_PROSE_DRIFT as a ratchet — it may shrink, never grow; each entry is
     a prose fix for the plugin docs, not a contract field to invent.
  2. the shapes RC-09 names are machine-readable `item_shape` entries.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp.contracts import PAGES, sections  # noqa: E402
from dma_mcp.vacuity import item_keys  # noqa: E402

PAGES_DIR = (ROOT / "plugins" / "dma-insights" / "skills"
             / "dma-surface-production" / "03-pages")
ROW = re.compile(r"^\|\s*`?([a-z_]+(?:\[\])?(?:\.[a-z_]+(?:\[\])?)*)`?\s*\|")

#: Prose rows naming a key the contract spells differently or not at all,
#: measured 2026-10-04. A ratchet: fix the prose (or the contract, where the
#: prose is right) and delete the entry; never add one to make a test pass.
KNOWN_PROSE_DRIFT = {
    ("H1", "focus_areas[].title"), ("H2", "freshness_band"),
    ("H5", "cap_ceiling"), ("O1", "overall_score"),
    ("O1", "pillar_scores[]"), ("O3", "signals[].body"),
    ("O3", "signals[].event_date"), ("O4", "scqa_md"),
    ("O4", "cited_e_ids"), ("O9", "context_tiles[]"), ("P3", "metrics"),
}


def _by_surface() -> dict:
    out: dict = {}
    for p in PAGES:
        for s, spec in sections(p).items():
            if isinstance(spec, dict):
                for sid in str(spec.get("surface_id") or "").replace(
                        " ", "").split(","):
                    out.setdefault(sid, []).append((p, s))
    return out


def _resolves(targets, parts) -> bool:
    for page, section in targets:
        spec = sections(page)[section]
        fields = spec["fields"]
        blob = json.dumps(spec)
        if parts[0] not in fields and parts[0] not in blob:
            continue
        if len(parts) == 1:
            return True
        keys = set(item_keys(page, section, parts[0])) \
            if parts[0] in fields else set()
        shape = (fields.get(parts[0]) or {}).get("item_shape") or {}
        if parts[-1] in keys or parts[-1] in shape or re.search(
                rf"\b{re.escape(parts[-1])}\b", blob):
            return True
    return False


def drift() -> set:
    by = _by_surface()
    out = set()
    for f in sorted(PAGES_DIR.glob("*/*.md")):
        if f.parent.name == "rulebooks" or f.stem not in by:
            continue
        text = f.read_text()
        if "### Information sources" not in text:
            continue
        block = text.split("### Information sources", 1)[1].split("\n### ", 1)[0]
        for line in block.splitlines():
            m = ROW.match(line)
            if m and not _resolves(by[f.stem], [x.rstrip("[]") for x in
                                                m.group(1).split(".")]):
                out.add((f.stem, m.group(1)))
    return out


def test_every_prose_field_resolves_in_the_contract():
    new = drift() - KNOWN_PROSE_DRIFT
    assert not new, (
        f"the page prose names fields the machine contract does not state: "
        f"{sorted(new)}. A field only the prose knows is optional in practice; "
        f"add it to contracts_data.json (field, item key or item_shape) or "
        f"correct the prose.")


def test_the_drift_ratchet_only_shrinks():
    stale = KNOWN_PROSE_DRIFT - drift()
    assert not stale, (f"{sorted(stale)} now resolve — delete them from "
                       f"KNOWN_PROSE_DRIFT so the ratchet tightens")


def test_the_rc09_shapes_are_machine_contract():
    plat = sections("platform")["platform_story"]["fields"]["platforms"]
    shape = plat.get("item_shape") or {}
    for k in ("peer_synthesis", "estate_reach", "peer_deployments",
              "peer_coverage"):
        assert k in shape, f"platforms item_shape does not state {k}"
    tiles = sections("context")["context_sentiment"]["fields"]["context_tiles"]
    assert "state" in (tiles.get("item_shape") or {}), \
        "context_tiles item_shape does not state `state`"
    assert "state" in item_keys("context", "context_sentiment", "context_tiles")
    themes = sections("overview")["sentiment"]["fields"]["themes"]
    assert "customer_projection" in (themes.get("item_shape") or {})
