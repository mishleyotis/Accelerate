"""The matching module: accurate where it can be, abstinent where it cannot,
and provably improved by the feedback ledger.

The negative controls matter more than the positives here: a matcher that
cannot be made to abstain, or whose ledger cannot flip a wrong answer, is
the matcher that quietly mis-files evidence — the defect the owner named.
"""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import subcap_match  # noqa: E402

CATALOGUE = [
    {"cell_id": "P4C2.5.1", "name": "Model inventory and documentation",
     "doc": "Model inventory and documentation. A registry of models with "
            "owner purpose and approval recorded, model governance."},
    {"cell_id": "P4C2.5.2", "name": "Model validation and testing",
     "doc": "Model validation and testing. Challenger model testing recorded "
            "against each registered model before production."},
    {"cell_id": "P3C1.2.1", "name": "Campaign audience segmentation",
     "doc": "Campaign audience segmentation. Marketing audiences built from "
            "member attributes with measurable activation."},
]


def test_the_right_cell_wins_on_a_clear_excerpt():
    ranked = subcap_match.rank(
        "the institution maintains a model registry with owner, purpose and "
        "approval recorded for every model", CATALOGUE)
    assert ranked[0]["cell_id"] == "P4C2.5.1"
    assert "registry" in ranked[0]["matched_terms"]
    verdict = subcap_match.decide(ranked, 0.05)
    assert verdict["decision"] == "MATCH"


def test_an_unrelated_excerpt_matches_nothing():
    ranked = subcap_match.rank(
        "quarterly board fees increased by four basis points", CATALOGUE)
    verdict = subcap_match.decide(ranked, 0.05)
    assert verdict["decision"] == "NO_MATCH"


def test_a_thin_margin_abstains_instead_of_guessing():
    """Two sibling model-governance cells share most vocabulary; an excerpt
    that names both concerns must NOT be auto-assigned."""
    ranked = subcap_match.rank(
        "model documentation and validation testing recorded", CATALOGUE)
    verdict = subcap_match.decide(ranked, min_margin=0.9)
    assert verdict["decision"] == "AMBIGUOUS"
    assert verdict["assign"] is None
    assert len(verdict["contenders"]) >= 2


def test_the_ledger_flips_a_near_miss(tmp_path):
    """The learning loop's whole point, as a test: before feedback the
    segmentation cell loses an 'audience activation' excerpt to nothing;
    after a confirmed boost it wins decisively."""
    excerpt = "activation journeys for member audiences"
    before = subcap_match.rank(excerpt, CATALOGUE)
    ledger = tmp_path / "fb.json"
    subcap_match.learn("P3C1.2.1", "confirmed",
                       ["activation", "journeys", "audiences"],
                       raised_by="qa-overseer", note="test", path=ledger)
    fb = subcap_match.load_feedback(ledger)
    after = subcap_match.rank(excerpt, CATALOGUE, fb)
    assert after[0]["cell_id"] == "P3C1.2.1"
    assert (not before or
            after[0]["score"] > next((r["score"] for r in before
                                      if r["cell_id"] == "P3C1.2.1"), 0.0))


def test_a_veto_removes_a_learned_wrong_association(tmp_path):
    """'segmentation' once dragged marketing excerpts onto the model cell;
    a rejected verdict must stop that cell scoring on the vetoed term."""
    poisoned = [dict(CATALOGUE[0],
                     doc=CATALOGUE[0]["doc"] + " segmentation segmentation"),
                CATALOGUE[2]]
    excerpt = "audience segmentation for campaigns"
    before = subcap_match.rank(excerpt, poisoned)
    ledger = tmp_path / "fb.json"
    subcap_match.learn("P4C2.5.1", "rejected", ["segmentation"],
                       raised_by="rectifier", path=ledger)
    after = subcap_match.rank(excerpt, poisoned,
                              subcap_match.load_feedback(ledger))
    assert after[0]["cell_id"] == "P3C1.2.1"
    assert before[0]["cell_id"] != "P3C1.2.1" or len(before) > 1


def test_ledger_refuses_an_entry_with_no_terms(tmp_path):
    with pytest.raises(SystemExit):
        subcap_match.learn("P4C2.5.1", "confirmed", [],
                           raised_by="x", path=tmp_path / "fb.json")


def test_ledger_stores_vocabulary_not_prose(tmp_path):
    ledger = tmp_path / "fb.json"
    subcap_match.learn("P4C2.5.1", "confirmed", ["Registry", "OWNER"],
                       raised_by="qa-overseer", path=ledger)
    d = json.loads(ledger.read_text())
    e = d["entries"][0]
    assert set(e) <= {"cell_id", "verdict", "terms", "raised_by", "on", "note"}
    assert e["terms"] == ["owner", "registry"]          # lowered, sorted
    # entries carry vocabulary fields only (the _doc explains the rule and
    # may name the word "excerpts"; the ENTRIES must never carry one)
    assert "excerpt" not in json.dumps(d["entries"])


def test_determinism_same_answer_twice():
    a = subcap_match.rank("model registry with approval recorded", CATALOGUE)
    b = subcap_match.rank("model registry with approval recorded", CATALOGUE)
    assert a == b
