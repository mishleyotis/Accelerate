"""Cluster A belt: apply_startup_data_fixes evidence-chip reconciliation +
str(dict)→prose. Pure-logic, no DB.

Root cause (measured across the shipped pack, 2026-07-08): 330 narrative
citations across 36/94 clients reference E-IDs absent from the client's own
evidence corpus (DOCX-scheme fabrications like E-500/E-607, and scheme-mismatch
clients whose research evidence E-001… was never persisted alongside the
E-INT-#### data-file rows). A chip that resolves to nothing == the live "evidence
drawer empty" symptom. This belt guarantees no dead chip ships, and renders a
recommendation solution dict that leaked as str(dict) back to prose.
"""
from __future__ import annotations

from collections import defaultdict

from app.scripts import apply_startup_data_fixes as m


def test_render_dict_prose_from_clean_repr() -> None:
    v = "{'solution': 'Salesforce Data Cloud', 'fit': 'Excellent — unifies client data.'}"
    out = m._render_dict_prose(v)
    assert out == "Salesforce Data Cloud — Excellent — unifies client data."
    assert not out.startswith("{'")


def test_render_dict_prose_from_truncated_repr() -> None:
    # A str(dict) cut at a char cap → literal_eval fails → regex fallback.
    v = ("{'solution': 'MuleSoft Anypoint Platform', 'from_catalog': 'Solution 5', "
         "'fit': 'Excellent — API-first enterprise, insurance connectors for Applied "
         "Epic, and BenefitPoint. The rest of this sentence is cut off ri")
    out = m._render_dict_prose(v)
    assert out.startswith("MuleSoft Anypoint Platform — Excellent")
    assert "{'" not in out and "from_catalog" not in out
    # trimmed back to a complete clause — no dangling fragment
    assert out.rstrip()[-1] in ".!?"


def test_render_dict_prose_passthrough_for_normal_prose() -> None:
    v = "Salesforce is the strongest-fit platform to modernize onboarding [E-040]."
    assert m._render_dict_prose(v) == v


def test_strip_dead_cites_keeps_resolvable_drops_dead() -> None:
    valid = {"E-021", "E-040"}
    txt = "Onboarding trails peers (currently 2.1) [E-021] with headroom [E-500]."
    out = m._tidy_prose(m._strip_dead_cites(txt, valid))
    assert "[E-021]" in out          # resolvable kept
    assert "E-500" not in out         # dead dropped
    assert "[]" not in out and "  " not in out
    assert out.endswith("headroom.")  # tidy: no space-before-period, no empty chip


def test_strip_dead_cites_partial_group() -> None:
    valid = {"E-040"}
    out = m._strip_dead_cites("The gap is acute [E-040, E-172, E-999].", valid)
    assert out == "The gap is acute [E-040]."  # kept only the resolvable id


def test_strip_dead_cites_all_dead_group_removed() -> None:
    valid = {"E-001"}
    out = m._tidy_prose(m._strip_dead_cites("Per the assessment [E-002, E-172] peers lead.", valid))
    assert "E-002" not in out and "E-172" not in out and "[]" not in out
    assert out == "Per the assessment peers lead."


def test_strip_leaves_text_when_no_valid_set() -> None:
    # Empty valid set → cannot know what's dead → never nuke everything.
    txt = "Onboarding trails peers [E-021]."
    obj = {"items": [{"what_text": txt}]}
    m._walk_reconcile(obj, set(), defaultdict(int))
    assert obj["items"][0]["what_text"] == txt


def test_walk_filters_eid_arrays_and_renders_dict() -> None:
    valid = {"E-040", "E-041"}
    obj = {
        "items": [
            {"what_text": "{'solution': 'Data Cloud', 'fit': 'Excellent — unifies data.'}",
             "linked_e_ids": ["E-040", "E-500", "E-041:F2", "E-999"],
             "counter_evidence_ids": ["E-041", "E-777"]},
        ]
    }
    stats: dict = defaultdict(int)
    changed = m._walk_reconcile(obj, valid, stats)
    assert changed
    it = obj["items"][0]
    assert it["what_text"].startswith("Data Cloud — Excellent")
    # dead E-IDs dropped from arrays; resolvable (incl. E-041:F2 base) kept
    assert it["linked_e_ids"] == ["E-040", "E-041:F2"]
    assert it["counter_evidence_ids"] == ["E-041"]
    assert stats["dict_prose_rendered"] == 1
    assert stats["dead_eid_dropped"] == 3


def test_eid_base_handles_schemes() -> None:
    assert m._eid_base("E-040") == "E-040"
    assert m._eid_base("E-040:F3") == "E-040"
    assert m._eid_base("E-INT-0233") == "E-INT-0233"
    assert m._eid_base("not-an-eid") is None
    assert m._eid_base(None) is None
