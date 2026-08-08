"""The findings memory's contracts, asserted without a database.

Four things this file refuses to let drift:

1. The vocabularies in `dma_mcp.memory` and the CHECK constraints in migration
   0034 are the same lists. A vocabulary that drifts between the writer and the
   column rejects at INSERT time with a constraint name and no advice, which is
   the least useful refusal available.
2. Dedup identity behaves as documented — the same defect worded differently is
   one finding, and a different component is a different finding.
3. The seed corpus would be ACCEPTED by `record_finding`'s own validation. A
   seed that the tool refuses is a seed that silently does not happen, which is
   this build's most-repeated shape (see STALE_BUILD_ARTEFACT_SERVED).
4. The migration graph has exactly ONE head. Three agents were allocated
   reserved revision numbers in the same tree during this build; two chains
   from the same parent is how `alembic upgrade head` starts refusing to run,
   and it fails at deploy time rather than here unless something asserts it.
"""
import importlib.util
import re
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import memory as mem                              # noqa: E402
from dma_mcp.seed_corpus import CORPUS                          # noqa: E402

MIGRATIONS = ROOT / "migrations" / "versions"


def _load_migration(name):
    """Import a revision module with `alembic.op` stubbed — the module bodies
    are pure data and functions; only `upgrade()` touches op."""
    path = MIGRATIONS / name
    stub = types.ModuleType("alembic")
    stub.op = types.SimpleNamespace(execute=lambda *a, **k: None,
                                    get_bind=lambda: None)
    sys.modules.setdefault("alembic", stub)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M0034 = _load_migration("0034_findings_memory.py")
M0035 = _load_migration("0035_defect_class_taxonomy.py")
SEEDED_CLASSES = {c[0] for c in M0035.CLASSES}


# ── 1. the vocabularies agree ───────────────────────────────────────────
@pytest.mark.parametrize("name", ["SEVERITIES", "STATUSES", "RAISERS",
                                  "TARGET_KINDS"])
def test_vocabularies_match_the_columns(name):
    assert tuple(getattr(mem, name)) == tuple(getattr(M0034, name)), (
        f"{name} differs between dma_mcp.memory and migration 0034; the "
        "column would reject a value the tool accepts")


def test_measurement_floor_matches_the_check_constraint():
    src = (MIGRATIONS / "0034_findings_memory.py").read_text()
    m = re.search(r"length\(btrim\(measurement\)\)\s*>=\s*(\d+)", src)
    assert m, "the measurement floor CHECK is no longer in 0034"
    assert int(m.group(1)) == mem.MEASUREMENT_FLOOR


def test_open_statuses_are_a_subset_of_the_status_vocabulary():
    assert set(mem.OPEN_STATUSES) <= set(mem.STATUSES)
    # RECURRED counts as open: a fix that did not hold is open again.
    assert "RECURRED" in mem.OPEN_STATUSES
    assert "RESOLVED" not in mem.OPEN_STATUSES


# ── 2. dedup identity ───────────────────────────────────────────────────
def test_the_same_defect_worded_differently_is_one_finding():
    a = mem.content_hash("mcp", "SILENT_HEADER_ALIAS_DROP",
                         "apps/worker/dma_worker/workbook_parser.py",
                         "A header spelling the parser does not know")
    b = mem.content_hash("MCP", "silent_header_alias_drop",
                         "apps/worker/dma_worker/workbook_parser.py",
                         "  A header   spelling the parser does not KNOW ")
    assert a == b, "case and whitespace must not split one defect in two"


def test_a_different_component_is_a_different_finding():
    args = ("SILENT_HEADER_ALIAS_DROP", "parser.py", "same title")
    assert mem.content_hash("worker", *args) != mem.content_hash("api", *args)


def test_a_different_locus_is_a_different_finding():
    assert (mem.content_hash("web", "STALE_BUILD_ARTEFACT_SERVED", "a.js", "t")
            != mem.content_hash("web", "STALE_BUILD_ARTEFACT_SERVED", "b.js", "t"))


def test_dedup_key_overrides_everything_else():
    k = mem.content_hash("web", "X", "a.js", "one title", dedup_key="fixed")
    assert k == mem.content_hash("api", "Y", "b.js", "other", dedup_key="fixed")


def test_locus_prefers_file_then_surface_then_gate():
    assert mem._locus({"file_path": "f", "surface": "H4", "gate_id": "CG-13"}) == "f"
    assert mem._locus({"surface": "H4", "gate_id": "CG-13"}) == "H4"
    assert mem._locus({"gate_id": "CG-13"}) == "CG-13"
    assert mem._locus({}) == ""


# ── 3. the seed corpus would be accepted ────────────────────────────────
REQUIRED = ("title", "observed", "measurement", "component", "defect_class",
            "severity", "raised_by_kind", "raised_by")


@pytest.mark.parametrize("entry", CORPUS,
                         ids=[e["finding"]["title"][:40] for e in CORPUS])
def test_every_seeded_finding_would_be_accepted(entry):
    f = entry["finding"]
    for key in REQUIRED:
        assert str(f.get(key) or "").strip(), f"{key} missing"
    assert len(f["measurement"].strip()) >= mem.MEASUREMENT_FLOOR, (
        "a finding that cannot say how it was measured is an opinion")
    assert f["severity"] in mem.SEVERITIES
    assert f["raised_by_kind"] in mem.RAISERS
    cls = f["defect_class"]
    if cls not in SEEDED_CLASSES:
        nc = f.get("new_class")
        assert isinstance(nc, dict), (
            f"{cls} is not seeded by 0035 and carries no new_class definition "
            "— record_finding would refuse it")
        for key in ("title", "description", "tell", "probe"):
            assert str(nc.get(key) or "").strip(), f"new_class.{key} missing"


@pytest.mark.parametrize("entry", [e for e in CORPUS if e.get("refinement")],
                         ids=[e["finding"]["title"][:40] for e in CORPUS
                              if e.get("refinement")])
def test_every_seeded_refinement_would_be_accepted(entry):
    r = entry["refinement"]
    assert r["target_kind"] in mem.TARGET_KINDS
    assert str(r.get("target") or "").strip()
    assert str(r.get("change") or "").strip()
    assert str(r.get("applied_by") or "").strip()
    assert r.get("commit_sha") or r.get("change_ref"), (
        "a refinement nobody can locate is a claim, not a change")


def test_a_recurrence_is_only_seeded_where_a_refinement_exists():
    for e in CORPUS:
        if e.get("recurrence"):
            assert e.get("refinement") and e.get("resolve"), (
                f"{e['finding']['title']!r} reports a recurrence with nothing "
                "that could have failed to hold")
            assert (len(e["recurrence"]["measurement"].strip())
                    >= mem.MEASUREMENT_FLOOR)


def test_the_corpus_covers_the_classes_this_build_produced():
    used = {e["finding"]["defect_class"] for e in CORPUS}
    # Every class 0035 seeds should have at least one measured instance,
    # except the reviewer class, which is seeded by real verdicts.
    unexercised = SEEDED_CLASSES - used - {"REVIEWER_REJECTED_INSIGHT"}
    assert not unexercised, (
        f"0035 defines {sorted(unexercised)} with no measured instance in the "
        "corpus — a class with no instance is a taxonomy nobody earned")


def test_the_corpus_records_at_least_one_fix_that_did_not_hold():
    assert any(e.get("recurrence") for e in CORPUS), (
        "recurrence is the signal that matters; a corpus with none of it "
        "cannot demonstrate the loop")


# ── 4. one migration head ───────────────────────────────────────────────
def test_the_migration_graph_has_exactly_one_head():
    revisions, downs = {}, {}
    for path in sorted(MIGRATIONS.glob("[0-9]*.py")):
        src = path.read_text()
        rev = re.search(r"^revision\s*=\s*[\"']([^\"']+)", src, re.M)
        down = re.search(r"^down_revision\s*=\s*(?:[\"']([^\"']+)[\"']|None)",
                         src, re.M)
        assert rev, f"{path.name} declares no revision"
        revisions[rev.group(1)] = path.name
        downs[rev.group(1)] = down.group(1) if down and down.group(1) else None
    parents = {d for d in downs.values() if d}
    heads = sorted(r for r in revisions if r not in parents)
    assert len(heads) == 1, (
        f"{len(heads)} migration heads: {[(h, revisions[h]) for h in heads]}. "
        "`alembic upgrade head` refuses to run with more than one, so the "
        "next revision must chain from the current head whatever its file "
        "number says.")
    missing = [d for d in downs.values() if d and d not in revisions]
    assert not missing, f"down_revision points at revisions that do not exist: {missing}"


def test_this_agents_revisions_are_the_three_it_was_allocated():
    mine = sorted(p.name for p in MIGRATIONS.glob("003[3-5]_*.py"))
    assert mine == ["0033_reviewer_feedback_path.py",
                    "0034_findings_memory.py",
                    "0035_defect_class_taxonomy.py"]


# ── the tools are declared ──────────────────────────────────────────────
MEMORY_TOOLS = ("record_finding", "search_findings", "list_open_findings",
                "get_finding", "list_defect_classes", "record_refinement",
                "resolve_finding", "report_recurrence", "get_memory_digest",
                "list_reviewer_feedback", "ingest_reviewer_feedback")


@pytest.mark.parametrize("tool", MEMORY_TOOLS)
def test_the_connector_declares_each_memory_tool(tool):
    src = (Path(__file__).resolve().parents[1] / "server.py").read_text()
    assert re.search(rf"^def {tool}\(", src, re.M), f"{tool} is not declared"
    # Every tool must sit under an @mcp.tool() decorator, or it is a function
    # nobody can call.
    block = src.split(f"def {tool}(")[0]
    assert block.rstrip().endswith("@_traced"), (
        f"{tool} is not wrapped by @_traced, so a server-side failure would "
        "reach the client as a verdict-shaped error with no traceback")


def test_every_memory_tool_docstring_states_its_contract():
    src = (Path(__file__).resolve().parents[1] / "server.py").read_text()
    for tool in MEMORY_TOOLS:
        body = src.split(f"def {tool}(", 1)[1]
        doc = body.split('"""')[1]
        assert len(doc) > 200, (
            f"{tool}'s docstring is {len(doc)} chars — these tools are read by "
            "agents instead of source, so the contract has to be in the "
            "docstring")
