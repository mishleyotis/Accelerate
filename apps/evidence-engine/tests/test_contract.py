"""The card contract, pinned (docs/CARD-CONTRACT.md)."""
import datetime as dt

from evidence_engine import contract as C


def _item(**kw):
    base = dict(source_name="Example Regulator — Call report, 2026 Q2",
                source_url="https://regulator.example.test/report/2026q2",
                excerpt="Total assets of $6.11 billion at June 30, 2026, up 4.2 percent over the year.",
                tier="T1", published_date="2026-08-15", claim_type="FACT",
                linked_subcap_ids=[], origin="producer")
    base.update(kw)
    return base


def test_clean_item_has_no_problems():
    assert C.item_problems(_item()) == []


def test_vocabularies_are_the_repos():
    assert C.TIERS == ("T1", "T2", "T3", "T4", "T5")
    assert C.CLAIM_LABELS == ("FACT", "INFERENCE", "HYPOTHESIS", "CEILING_ESTIMATE")
    assert C.RECENCY_WORDS == ("CURRENT", "RECENT", "DATED", "STALE", "ARCHIVAL", "UNVERIFIED")
    assert "LEGACY" not in C.RECENCY_WORDS


def test_claim_label_is_the_one_the_tier_licenses():
    assert C.claim_label_for("T1") == "FACT"
    assert C.claim_label_for("T2") == "FACT"
    for t in ("T3", "T4", "T5"):
        assert C.claim_label_for(t) == "INFERENCE"
    assert C.Item("n", "https://x.test/", "x" * 60, "T3").claim_type == "INFERENCE"


def test_recency_band_matches_the_connectors_arithmetic():
    ref = dt.date(2026, 10, 10)
    assert C.recency_band("2026-10-01", ref) == "CURRENT"
    assert C.recency_band("2025-10-10", ref) == "CURRENT"      # 12 months inclusive
    assert C.recency_band("2025-09-10", ref) == "RECENT"
    assert C.recency_band("2024-09-10", ref) == "DATED"
    assert C.recency_band("2023-09-10", ref) == "STALE"
    assert C.recency_band("2022-09-10", ref) == "ARCHIVAL"
    assert C.recency_band(None, ref) == "UNVERIFIED"
    assert C.recency_band("2027-01-01", ref) == "UNVERIFIED"   # future is a plan, not a date
    assert C.recency_band("15 March 2026", ref) == "UNVERIFIED"  # DMY would be undated


def test_excerpt_length_rules():
    assert any("excerpt_length" in p for p in C.item_problems(_item(excerpt="Too short. Yes.")))
    assert any("excerpt_length" in p for p in C.item_problems(_item(excerpt="A" + "a" * 500 + ".")))


def test_clause_truncation_is_refused_like_the_connector():
    clipped = "x" * 139 + "a"            # exactly 140, ends in a word char
    assert C.clause_truncated(clipped)
    assert C.clause_truncated(clipped + " | " + clipped)
    assert C.clause_truncated("x" * 139 + ".") is None


def test_sentence_completeness():
    assert C.sentence_complete("Members grew 4.2 percent to 212,000 in 2025.")
    assert C.sentence_complete("Revenue was $12.4 million (up 8%)")
    assert C.sentence_complete("The ratio stood at 11.2%")
    assert not C.sentence_complete("BCU ranked #1 in proactive guidance among all Tethr users; excelled in action-fo")
    assert not C.sentence_complete("including:")
    assert not C.sentence_complete("the credit union said it would")
    assert not C.sentence_complete("and")
    assert not C.sentence_complete("")


def test_fact_on_weak_tier_is_refused():
    probs = C.item_problems(_item(tier="T3", claim_type="FACT"))
    assert any("fact_tier" in p for p in probs)


def test_dates_must_be_iso():
    assert any("published_date" in p for p in C.item_problems(_item(published_date="15 March 2026")))
    assert any("future" in p for p in C.item_problems(_item(published_date="2099-01-01")))
    assert C.item_problems(_item(published_date=None)) == []


def test_engine_never_links_cells_or_changes_origin():
    assert any("linked_subcap_ids" in p for p in C.item_problems(_item(linked_subcap_ids=["P1C1.1.1"])))
    assert any("origin" in p for p in C.item_problems(_item(origin="connector")))


def test_own_domain_is_never_t1():
    probs = C.item_problems(_item(source_url="https://www.example-fcu.test/annual-report"),
                            own_hosts={"example-fcu.test"})
    assert any("own_domain_t1" in p for p in probs)
    assert C.item_problems(_item(source_url="https://www.example-fcu.test/annual-report", tier="T2"),
                           own_hosts={"example-fcu.test"}) == []


def test_source_name_abbreviations_are_refused():
    probs = C.item_problems(_item(source_name="NCUA call report"), abbreviations={"NCUA": "x"})
    assert any("source_name_abbreviation" in p for p in probs)


def test_engine_flags_render_exactly():
    card = {"item": _item()}
    argv = C.item_to_engine_flags(card, subcaps=["P1C1.1.1", "P1C1.1.2"], actor="research-p1c1-collector")
    assert argv[:3] == ["evidence", "--source", card["item"]["source_name"]]
    assert "--published" in argv and argv[argv.index("--published") + 1] == "2026-08-15"
    assert argv.count("--subcap") == 2
    assert argv[argv.index("--origin") + 1] == "public"
    assert argv[-2:] == ["--actor", "research-p1c1-collector"]
    assert "--published" not in C.item_to_engine_flags({"item": _item(published_date=None)}, subcaps=[])


def test_card_serialises_with_minimal_provenance():
    card = C.Card("EV-00000000", C.Item(**_item()), C.Provenance(recency="CURRENT", origin_cluster="OC-1",
                                                                 context_handle="CTX-1", entity_match="confirmed"))
    full = card.to_dict()
    assert set(full) == {"card_id", "item", "provenance"}
    assert full["item"] == _item()
    mini = card.to_dict(provenance="minimal")
    assert set(mini["provenance"]) == {"url_status", "recency", "entity_match", "origin_cluster", "context_handle"}


def test_ids_are_stable_hashes():
    a = C.card_id_for("https://x.test/a", "Some   Excerpt here.")
    b = C.card_id_for("https://x.test/a", "some excerpt HERE.")
    assert a == b and a.startswith("EV-") and len(a) == 11
    assert C.context_handle_for("sha256:abc", 1, 2).startswith("CTX-")


def test_token_estimate_is_positive():
    assert C.estimate_tokens({"a": "b" * 40}) >= 10
