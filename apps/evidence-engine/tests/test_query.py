"""query.expand / query.guard."""
from __future__ import annotations

import pytest

from evidence_engine import query
from evidence_engine.contract import FACETS
from evidence_engine.types import EntityRef

ENTITY = EntityRef(legal_name="Example Federal Credit Union",
                   domains=["example-fcu.test", "https://www.online.example-fcu.test/"],
                   aliases=["Example FCU"], sub_vertical="credit union")
QUESTION = ("To what extent has the organization established a documented digital "
            "onboarding journey with identity verification for new members?")
PACK = ["ncua.gov", "cutimes.com", "americanbanker.com", "creditunions.com",
        "thefinancialbrand.com", "cuinsight.com", "bankingdive.com", "finopotamus.com"]


def test_five_facets_with_ids_and_quoted_name():
    qs = query.expand(QUESTION, ENTITY, None, None, None)
    facet_qs, own = qs[:5], qs[5:]
    assert [q["facet"] for q in facet_qs] == list(FACETS)
    assert [q["query_id"] for q in qs] == [f"Q-{i:02d}" for i in range(1, 8)]
    for q in facet_qs:
        assert q["text"].startswith('"Example Federal Credit Union"')
        assert q["kind"] == "facet"
        assert "onboarding" in q["text"] and "extent" not in q["text"]
    assert "launched" in facet_qs[0]["text"] and "complaint" in facet_qs[1]["text"]
    assert [q["kind"] for q in own] == ["site_own", "site_own"]      # own domains, no pack


def test_site_variants_and_cap():
    qs = query.expand(QUESTION, ENTITY, None, "credit union", PACK)
    assert len(qs) == query.MAX_QUERIES == 12
    assert [q["query_id"] for q in qs] == [f"Q-{i:02d}" for i in range(1, 13)]
    own = [q for q in qs if q["kind"] == "site_own"]
    assert [q["text"].split()[0] for q in own] == ["site:example-fcu.test", "site:online.example-fcu.test"]
    pack = [q for q in qs if q["kind"] == "site_pack"]
    assert pack and pack[0]["text"].startswith("site:ncua.gov")
    assert '"credit union"' in pack[0]["text"]
    assert all(q["facet"] in FACETS for q in qs)


def test_single_facet_only():
    qs = query.expand(QUESTION, ENTITY, "fails", None, ["ncua.gov"])
    assert {q["facet"] for q in qs} == {"fails"}
    assert len(qs) == 1 + 2 + 1


def test_unknown_facet_refused():
    with pytest.raises(ValueError):
        query.expand(QUESTION, ENTITY, "rumours", None, None)


def test_expand_is_deterministic():
    a = query.expand(QUESTION, ENTITY, None, "credit union", PACK)
    b = query.expand(QUESTION, ENTITY, None, "credit union", list(PACK))
    assert a == b


def test_guard_refuses_an_injected_vendor_name():
    qs = query.expand(QUESTION, ENTITY, None, None, None)
    qs.append({"query_id": "Q-99", "text": '"Example Federal Credit Union" Jack Henry Symitar core', "facet": "works", "kind": "facet"})
    clean, violations = query.guard(qs, None)
    assert [q["query_id"] for q in clean] == [f"Q-{i:02d}" for i in range(1, 8)]
    refused = [v for v in violations if v["kind"] == "refused"]
    assert {v["name"] for v in refused} == {"Jack Henry", "Symitar"}
    assert all(v["query_id"] == "Q-99" for v in refused)


def test_guard_exception_path_records_the_card():
    qs = [{"query_id": "Q-01", "text": '"Example Federal Credit Union" Alkami digital banking', "facet": "works", "kind": "facet"}]
    clean, violations = query.guard(qs, {"alkami": ["EV-0badcafe"]})
    assert clean == qs
    assert violations == [{"query_id": "Q-01", "text": qs[0]["text"], "name": "Alkami",
                           "kind": "exception", "card_id": "EV-0badcafe", "card_ids": ["EV-0badcafe"]}]


def test_guard_word_boundary_and_multiword():
    # "Fiserv" inside another token is not a hit; "jack  henry" with odd spacing is
    assert query.find_names("the fiservice desk") == []
    assert query.find_names("JACK   henry core") == ["Jack Henry"]
    assert query.find_names("microsoft dynamics 365 crm") == ["Microsoft Dynamics"]
    assert query.find_names("a blend of services") == []


def test_guard_is_idempotent():
    qs = query.expand(QUESTION, ENTITY, None, None, PACK)
    qs.append({"query_id": "Q-13", "text": "Temenos", "facet": "works", "kind": "facet"})
    clean, v1 = query.guard(qs, None)
    clean2, v2 = query.guard(clean, None)
    assert clean2 == clean and v2 == [] and len(v1) == 1


def test_platform_list_is_substantial_and_free_of_english_words():
    names = query.platform_names()
    assert len(names) >= 60
    for word in ("Blend", "Alloy", "Encompass", "Segment"):
        assert word not in names
