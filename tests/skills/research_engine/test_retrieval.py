"""RRF fusion, BM25 rerank with abstain, and query planning."""
import pytest

from engine import retrieval as R


def _lists():
    return [
        # presence-shaped query
        [{"url": "https://acme.example/ar25", "title": "Annual Report 2025",
          "snippet": "digital strategy refresh cadence board"},
         {"url": "https://news.example/a", "title": "Acme launches app"},
         {"url": "https://blog.example/x", "title": "Acme blog"}],
        # responsiveness-shaped query
        [{"url": "https://www.acme.example/ar25?utm_source=x",
          "title": "Annual Report 2025",
          "snippet": "the digital strategy is refreshed annually and "
                     "reviewed by the board with success criteria"},
         {"url": "https://filings.example/10k", "title": "10-K"},
         {"url": "https://news.example/a"}],
        # toolkit-artefact query
        [{"url": "https://acme.example/ar25/"},
         {"url": "https://jobs.example/posting"}],
    ]


# ── RRF ──────────────────────────────────────────────────────────────────

def test_consensus_beats_a_single_first_place():
    """The Cormack property: ranked by three lists at #1/#1/#1-equivalent
    positions beats #2 in one list only."""
    fused = R.rrf(_lists())
    assert fused[0]["url"].startswith("https://acme.example/ar25")
    assert fused[0]["lists_ranking_it"] == 3


def test_the_same_source_under_url_variants_is_one_source():
    """www., trailing slash and utm_ tracking do not make three sources —
    they make one source counted three times, which is fake consensus."""
    fused = R.rrf(_lists())
    ar = [x for x in fused if "acme.example/ar25" in x["url"]]
    assert len(ar) == 1


def test_the_fusion_is_auditable():
    fused = R.rrf(_lists())
    top = fused[0]
    assert set(top["provenance"]) == {"0", "1", "2"}
    assert all(isinstance(v, int) for v in top["provenance"].values())


def test_k_is_cormacks_sixty():
    assert R.RRF_K == 60


def test_rrf_exact_arithmetic():
    fused = R.rrf([[{"url": "https://a.example/x"}],
                   [{"url": "https://a.example/x"},
                    {"url": "https://b.example/y"}]])
    a = next(x for x in fused if "a.example" in x["url"])
    b = next(x for x in fused if "b.example" in x["url"])
    assert a["rrf_score"] == round(1 / 61 + 1 / 61, 6)
    assert b["rrf_score"] == round(1 / 62, 6)


def test_richest_snippet_survives_the_merge():
    fused = R.rrf(_lists())
    assert "success criteria" in fused[0]["snippet"]


# ── BM25 rerank + abstain ────────────────────────────────────────────────

QUESTION = ("To what extent is a formal, documented digital strategy "
            "established, and is there a defined cadence for refreshing it?")


def test_the_responsive_document_outranks_the_merely_popular():
    out = R.rerank(QUESTION, R.rrf(_lists()))
    assert out["ranked"], out
    assert "ar25" in out["ranked"][0]["url"]


def test_noise_abstains_instead_of_ranking():
    """AUD-0075's failure: a mapper with no abstain path filed a county-fair
    mascot under Fair Lending Governance. Zero-overlap noise must land in
    below_floor, never in the ranking."""
    noise = [{"url": "https://fair.example/mascot",
              "title": "Mascot appears at the county fair",
              "snippet": "a rotating exhibit of works by local painters"}]
    out = R.rerank(QUESTION, R.rrf([noise]))
    assert out["ranked"] == []
    assert len(out["below_floor"]) == 1


def test_below_floor_is_returned_not_dropped():
    out = R.rerank(QUESTION, R.rrf(_lists()))
    total = len(out["ranked"]) + len(out["below_floor"])
    assert total == len(R.rrf(_lists()))


# ── query planning ───────────────────────────────────────────────────────

def test_the_plan_carries_three_differently_shaped_probes():
    qs = R.plan_queries(
        "Acme Credit Union", "Digital Strategy Document", "works",
        QUESTION, public_sources="1) Annual Report—strategy section; "
                                 "2) Investor presentation")
    assert any("went live" in q or "rollout" in q for q in qs)   # presence
    assert any("cadence" in q or "refreshing" in q for q in qs)  # responsive
    assert any('"Annual Report' in q for q in qs)                # artefact
    assert all(q.startswith('"Acme Credit Union"') for q in qs)
    assert len(qs) == len(set(qs))


def test_the_responsive_probe_carries_the_questions_own_words():
    """AUD-0074: 40% of DQ/query pairs had no responsive query — the works
    DQ asked for a fifteen-year arc and the query asked 'annual review'."""
    qs = R.plan_queries("Acme CU", None, "value",
                        "Which decisions does the capability make faster, "
                        "cheaper or more accountable, and where is that "
                        "measured?")
    assert any("decisions" in q and "accountable" in q for q in qs)


def test_an_unknown_facet_is_refused():
    with pytest.raises(ValueError):
        R.plan_queries("Acme", None, "vibes", "?")
