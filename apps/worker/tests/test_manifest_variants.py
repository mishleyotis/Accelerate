"""The shipped corpus's manifests are heterogeneous — every synthesis
run authored its own schema. One normaliser resolves identity, stated
overall and stated dates; nothing downstream guesses (prod failure
classes: institution-as-string, entity-as-string/dict, entity_name,
top-level overall_score, non-dict versions)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.persist import _institution, _stated_completed_at, _stated_overall


def test_institution_shapes_resolve_to_one_dict():
    assert _institution({"institution": {"name": "Canonical Bank", "sub_vertical": "CIB"}})["name"] == "Canonical Bank"
    assert _institution({"institution": "String Bank"})["name"] == "String Bank"
    assert _institution({"entity_name": "APG Federal Credit Union"})["name"] == "APG Federal Credit Union"
    assert _institution({"institution_name": "Amarillo National Bank"})["name"] == "Amarillo National Bank"
    assert _institution({"entity": "Bell Bank"})["name"] == "Bell Bank"
    d = _institution({"entity": {"name": "Amalgamated Bank", "sub_vertical": "Regional Banks"}})
    assert d["name"] == "Amalgamated Bank" and d["sub_vertical"] == "Regional Banks"
    assert _institution({}) == {}
    assert _institution({"subvertical": "Credit Unions"})["sub_vertical"] == "Credit Unions"


def test_stated_overall_reads_both_shapes_never_derives():
    assert _stated_overall({"scores": {"overall": 2.4}}) == 2.4
    assert _stated_overall({"overall_score": 3.1}) == 3.1
    assert _stated_overall({"scores": "not a dict"}) is None
    assert _stated_overall({"overall_score": "2.9ish"}) is None
    assert _stated_overall({}) is None


def test_stated_completed_at_iso_or_nothing():
    assert _stated_completed_at({"assessment": {"date": "2026-03-12"}}) == "2026-03-12"
    assert _stated_completed_at({"generated_at": "2026-04-28T13:00:00Z"}).startswith("2026-04-28")
    assert _stated_completed_at({"assessment_date": "Q2 2026"}) is None
    assert _stated_completed_at({"assessment": "March"}) is None
    assert _stated_completed_at({}) is None
