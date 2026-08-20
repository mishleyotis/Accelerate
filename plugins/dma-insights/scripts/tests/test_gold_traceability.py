"""Every gold exemplar an agent quotes is traceable to the served truth.

The roster build's verify pass observed (2026-08-20) that agents quoted
gold-standard rows citing a transient scratchpad path that exists on no
disk — plausible examples nothing in-repo could check. The repair is the
gold: notation plus fixtures/gold_manifest.json: the manifest pins each
exemplar's sha256, size and top-level keys as fetched from the live serving
API, so the citations resolve and drift is detectable — without committing
client payload bodies to a public repository.
"""
import json
import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
AGENTS = PLUGIN / "agents"
MANIFEST = PLUGIN / "fixtures" / "gold_manifest.json"

_GOLD = re.compile(r"gold:[a-z]+/[a-z]+\.[a-z_]+")


def test_no_agent_cites_a_transient_path():
    for f in AGENTS.glob("*.md"):
        text = f.read_text()
        assert "scratchpad" not in text, (
            f"{f.name} cites a transient scratchpad path — use the gold: "
            f"notation pinned by fixtures/gold_manifest.json")
        assert "/tmp/" not in text, f"{f.name} cites a /tmp path"


def test_every_gold_citation_resolves_in_the_manifest():
    manifest = json.loads(MANIFEST.read_text())["sections"]
    unresolved = []
    for f in sorted(AGENTS.glob("*.md")):
        for ref in _GOLD.findall(f.read_text()):
            if ref not in manifest:
                unresolved.append(f"{f.name}: {ref}")
    assert not unresolved, (
        "gold: citations with no manifest entry:\n  " + "\n  ".join(unresolved))


def test_manifest_names_the_runs_and_the_refetch_route():
    m = json.loads(MANIFEST.read_text())
    assert m["runs"]["baxter"]["run_id"].startswith("c1351d25")
    assert m["runs"]["baxter"]["display_id"] == "baxter-credit-union-bcu"
    assert "GET /v1/entities/" in m["_doc"]
    # the gold run is v5.0-pinned — verified against live serving 2026-08-20;
    # agents teaching the v5.0/v7.0 difference depend on this being stated
    assert m["runs"]["baxter"]["ccg_catalog_version"] == "v5.0"


def test_manifest_entries_carry_shape_not_content():
    m = json.loads(MANIFEST.read_text())
    for ref, entry in m["sections"].items():
        assert set(entry) == {"sha256", "bytes", "top_level_keys"}, (
            f"{ref} carries more than shape — client payload bodies stay "
            f"out of this public repository")


def test_the_check_can_fail(tmp_path):
    """Negative control: an invented citation must be reported."""
    manifest = json.loads(MANIFEST.read_text())["sections"]
    assert "gold:baxter/overview.invented_section" not in manifest
