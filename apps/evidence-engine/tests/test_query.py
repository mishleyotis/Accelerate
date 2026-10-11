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
    facet_qs = qs[:5]
    assert [q["facet"] for q in facet_qs] == list(FACETS)
    assert [q["query_id"] for q in qs] == [f"Q-{i:02d}" for i in range(1, len(qs) + 1)]
    for q in facet_qs:
        assert q["text"].startswith('"Example Federal Credit Union"')
        assert q["kind"] == "facet"
        assert "onboarding" in q["text"] and "extent" not in q["text"]
        assert " OR " not in q["text"], "operators are gone: one lens word per facet"
        assert len(q["text"].replace('"Example Federal Credit Union"', "").split()) <= 6
    assert facet_qs[0]["text"].endswith(" launches") and facet_qs[1]["text"].endswith(" complaint")
    own = [q for q in qs if q["kind"] == "site:entity"]
    assert len(own) == 2 and not [q for q in qs if q["kind"].startswith("site:") and q["kind"] != "site:entity"]   # own domains, no pack
    alias = [q for q in qs if q["kind"] == "alias"]
    assert alias and alias[0]["text"].startswith("Example FCU ")


def test_site_variants_and_cap():
    qs = query.expand(QUESTION, ENTITY, None, "credit union", PACK)
    assert len(qs) <= query.MAX_QUERIES == 16
    assert [q["query_id"] for q in qs] == [f"Q-{i:02d}" for i in range(1, len(qs) + 1)]
    own = [q for q in qs if q["kind"] == "site:entity"]
    assert [q["text"].split()[0] for q in own] == ["site:example-fcu.test", "site:online.example-fcu.test"]
    pack = [q for q in qs if q["kind"].startswith("site:") and q["kind"] != "site:entity"]
    assert pack and pack[0]["text"].startswith("site:ncua.gov")
    assert "Example FCU" in pack[0]["text"], "a pack probe names the entity by its short alias"
    assert all(q["facet"] in FACETS for q in qs)


def test_single_facet_only():
    qs = query.expand(QUESTION, ENTITY, "fails", None, ["ncua.gov"])
    assert {q["facet"] for q in qs} == {"fails"}
    kinds = [q["kind"] for q in qs]
    assert kinds.count("facet") == 1 and kinds.count("site:entity") == 2 and kinds.count("site:news") == 1


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
    assert [q["query_id"] for q in clean] == [q["query_id"] for q in qs if q["query_id"] != "Q-99"]
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


def test_pack_entries_carry_their_ladder_rung_into_the_query_kind():
    pack = [{"domain": "ncua.gov", "rung": "regulator"}, {"domain": "cutimes.com", "rung": "trade_press"}, "prnewswire.com"]
    qs = query.expand(QUESTION, ENTITY, None, "credit union", pack)
    kinds = [q["kind"] for q in qs if q["kind"].startswith("site:") and q["kind"] != "site:entity"]
    assert kinds == ["site:regulator", "site:trade_press", "site:news"]


def test_registry_site_pack_follows_the_sub_vertical():
    from evidence_engine import registry
    assert registry.site_pack("Credit Unions")[0] == {"domain": "ncua.gov", "rung": "regulator"}
    assert registry.site_pack("CU")[0]["domain"] == "ncua.gov"
    assert registry.site_pack("Regional Banks")[0]["domain"] == "fdic.gov"
    assert registry.site_pack("Insurance Brokers")[0]["domain"] == "naic.org"
    assert registry.site_pack("RIAs & Broker-Dealers")[0]["domain"] == "sec.gov"
    assert registry.site_pack("Commercial Lending")[0]["domain"] == "consumerfinance.gov"
    assert registry.site_pack(None)[0]["rung"] == "news" and len(registry.site_pack(None)) <= 6
