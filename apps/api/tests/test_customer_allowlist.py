"""The customer serve boundary is an allowlist, and it fails closed.

Every deny rule in redaction.py was added after a measured leak; this file
pins the flipped default. The defining test is the first one: a key the
contract never named — the internal artifact nobody thought to deny —
must NOT reach a customer body, and the drop must be receipted.
"""
import json
import subprocess
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.redaction import redact_section  # noqa: E402


def _cells_body():
    return {
        "produced_at": "2026-08-19T00:00:00Z",
        "producer_version": "test",
        "e_ids": ["E-XX-001"],
        "internal_only": [],
        "narrative_thread": "thread",
        "linking_stats": {"cells_linked": 1},
        "empty_state": {"reason": "a real reason",
                        "closure_condition": "what would close it",
                        "sources_searched": ["host.example — nil"],
                        "searched_on": "2026-08-18"},
        "cells": [{
            "subcap_id": "P1C1.1.1",
            "synthesis": "the argument",
            "grounded_on": 1,
            "e_ids": ["E-XX-001"],
            "thin": False,
            "reach_note": "reaches",
            "closure_condition": "a span naming the practice",
            "sources_searched": ["site: example.com — nil"],
            "provenance": "declared",
            "items": [{"e_id": "E-XX-001", "excerpt": "x" * 60,
                       "tier": "T2", "claim_label": "FACT"}],
            "a_key_nobody_classified": "internal-shaped surprise",
        }],
    }


def test_an_unclassified_key_never_reaches_a_customer_body():
    out, report = redact_section("heatmap", "cell_evidence", _cells_body(),
                                 [], "customer")
    assert out is not None
    cell = out["cells"][0]
    assert "a_key_nobody_classified" not in cell
    assert any("a_key_nobody_classified" in d
               for d in report["allowlist_dropped"])


def test_probe_ladders_are_dropped_and_the_reason_survives():
    out, _ = redact_section("heatmap", "cell_evidence", _cells_body(),
                            [], "customer")
    cell = out["cells"][0]
    assert "sources_searched" not in cell
    es = out["empty_state"]
    assert "sources_searched" not in es and "searched_on" not in es
    assert es["reason"] == "a real reason"
    assert es["closure_condition"] == "what would close it"


def test_method_vocabulary_is_dropped_from_drawer_items():
    out, _ = redact_section("heatmap", "cell_evidence", _cells_body(),
                            [], "customer")
    item = out["cells"][0]["items"][0]
    assert "tier" not in item
    assert item["excerpt"].startswith("x")


def test_the_internal_audience_is_untouched_by_the_allowlist():
    out, report = redact_section("heatmap", "cell_evidence", _cells_body(),
                                 [], "internal")
    cell = out["cells"][0]
    assert "sources_searched" in cell and "provenance" in cell
    assert "a_key_nobody_classified" in cell
    assert "allowlist_dropped" not in report


def test_an_unknown_section_is_withheld_not_served():
    out, report = redact_section("heatmap", "invented_section",
                                 {"produced_at": "x", "stuff": 1},
                                 [], "customer")
    assert out is None
    assert report["withheld"] and report.get("unknown_section")


def test_the_committed_allowlist_covers_a_fresh_generation():
    """A contract change that widens the serve surface fails here until the
    new key is classified — the fail-closed property, pinned in CI.

    REWRITTEN 2026-08-20 because the previous version could not fail and
    damaged the repo while not failing. It ran the generator with no
    arguments — which OVERWRITES the tracked allowlist — and then compared
    the file to itself, both reads taken after the write. Two consequences,
    both measured: the assertion was tautological, and any `git add -A` after
    a test run committed a silently regenerated allowlist. One did: 49 keys
    left the customer serve surface in a commit whose message was about
    something else entirely.

    The generation now goes to a temporary path, and the assertion is the
    one that carries the intent: every key a fresh generation would serve
    must already be named in the committed file. The committed file may be
    WIDER — it is, deliberately, and the extras are keys the deny passes
    strip before the allowlist ever runs (contact routes, r_layer) plus
    client content the generator's classification does not yet recognise —
    but it may never be NARROWER, because that is the direction in which a
    new contract key reaches a client unclassified.
    """
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / "generated.json"
        gen = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "gen_customer_allowlist.py"),
             "--out", str(fresh)],
            capture_output=True, text=True, cwd=ROOT)
        assert gen.returncode == 0, gen.stderr
        generated = json.loads(fresh.read_text())
    committed = json.loads(
        (ROOT / "apps" / "api" / "dma_api" / "customer_allowlist.json")
        .read_text())
    assert len(committed["sections"]) == 34
    unclassified = []
    for sec, spec in generated["sections"].items():
        have = committed["sections"].get(sec)
        assert have is not None, f"{sec} is served but not in the allowlist"
        unclassified += [f"{sec}.{k}" for k in spec.get("keys", [])
                         if k not in have.get("keys", [])]
        for field, keys in (spec.get("items") or {}).items():
            have_keys = (have.get("items") or {}).get(field, [])
            unclassified += [f"{sec}.{field}.{k}" for k in keys
                             if k not in have_keys]
    assert not unclassified, (
        "the contract serves keys the allowlist does not name: "
        + ", ".join(unclassified[:20]))


def test_regenerating_the_allowlist_never_touches_the_tracked_file():
    """The damage half of the same defect, pinned on its own.

    A generator that writes the repo by default is one careless `git add`
    away from a serving-surface change nobody reviewed, so the test suite
    must never invoke it that way.
    """
    tracked = ROOT / "apps" / "api" / "dma_api" / "customer_allowlist.json"
    before = tracked.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "x.json"
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "gen_customer_allowlist.py"),
             "--out", str(out)], capture_output=True, text=True, cwd=ROOT)
        assert out.is_file()
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_customer_allowlist.py"),
         "--check"], capture_output=True, text=True, cwd=ROOT)
    assert tracked.read_bytes() == before, (
        "--out or --check rewrote the tracked allowlist")
    src = (ROOT / "apps" / "api" / "tests" / "test_customer_allowlist.py").read_text()
    assert "gen_customer_allowlist.py\")]" not in src.replace(" ", ""), (
        "a test invokes the generator with no --out/--check and will "
        "overwrite the tracked file")


def test_excluded_classes_cover_the_measured_logix_leaks():
    allow = json.loads(
        (ROOT / "apps" / "api" / "dma_api" / "customer_allowlist.json")
        .read_text())
    excluded = set(allow["excluded_key_classes"])
    for k in ("sources_searched", "queries_run", "searched_on",
              "tier", "ers", "discovered_by", "cap_level"):
        assert k in excluded, f"{k} is not excluded — the measured leak class"


def test_the_reference_fixture_is_not_empty():
    """The allowlist is GENERATED from this fixture, so an empty fixture is
    not a small customer surface — it is a missing input that silently
    narrows what every client can see. It shipped empty once (2026-08-20)
    and cost 49 keys before anyone noticed."""
    ref = json.loads(
        (ROOT / "fixtures" / "reference_surface_keys.json").read_text())
    assert ref.get("sections"), (
        "fixtures/reference_surface_keys.json has no sections — recover it "
        "with: git checkout ff79471 -- fixtures/reference_surface_keys.json")
    assert len(ref["sections"]) == 34, (
        f"the reference covers {len(ref['sections'])} sections, not 34")


def test_generation_from_an_empty_reference_refuses():
    """The guard, asserted against the REAL corrupt shape.

    The first version of this guard tested the truthiness of the fixture's
    non-underscore keys — and the corrupt shape is
    {"_doc": ..., "sections": {}}, which has one such key and is therefore
    truthy. The guard never fired on the only input it was written for. A
    test that used a bare {} would have passed just as vacuously, so this
    one writes the shape that actually occurred.
    """
    fixture = ROOT / "fixtures" / "reference_surface_keys.json"
    original = fixture.read_bytes()
    try:
        fixture.write_text(json.dumps({"_doc": "placeholder", "sections": {}}))
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [sys.executable,
                 str(ROOT / "scripts" / "gen_customer_allowlist.py"),
                 "--out", str(Path(tmp) / "out.json")],
                capture_output=True, text=True, cwd=ROOT)
        assert r.returncode != 0, (
            "the generator accepted an empty reference and produced an "
            "allowlist from it")
        assert "refusing to narrow" in r.stderr, r.stderr[:300]
    finally:
        fixture.write_bytes(original)
