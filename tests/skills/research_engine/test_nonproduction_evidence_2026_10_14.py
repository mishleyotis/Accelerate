"""A test/staging copy of a site is never evidence.

AAA Western and Central New York (2026-10-14): E-194 cited
test.westerncentralnyaaa.com, a pre-production copy of the club's site. Every
Evidence_Detail row ships in the package's evidence index, so the client view
would have carried a test-host link. The write now refuses a pre-production
host; `retire_nonproduction_evidence` removes one registered before the rule
— never one that prose still cites — and `repoint_evidence` moves a cited one
to the production copy of the same page once the span is verified there.
"""
import pytest

from engine import contract as C
from engine import ledger as L
from engine.workbook import _split_ids

from fixtures import new_run

SPAN = ("Our Refer a Friend rewards program will reward you with a gift card for "
        "every eligible friend who joins.")


def _cell(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False, folder=False)
    wb = run.open()
    return run, wb, wb.selected_subcaps()[0]


@pytest.mark.parametrize("url,bad", [
    ("https://test.example-club.com/refer", True),
    ("https://staging.example-club.com/refer", True),
    ("https://dev.example-club.com/refer", True),
    ("https://example-club.com/refer", False),
    ("https://www.example-club.com/refer", False),
    ("https://dev.to/article", False),                  # a registrable domain, not a subdomain
])
def test_nonproduction_host_reads_only_a_subdomain_label(url, bad):
    assert bool(L.nonproduction_host(url)) is bad


def test_the_write_refuses_a_staging_host(tmp_path):
    run, wb, cell = _cell(tmp_path)
    with pytest.raises(L.LedgerRefusal, match="non-production host"):
        L.append_evidence(wb, source_name="Club refer-a-friend (test site)",
                          source_url="https://test.example-club.com/refer",
                          tier="T5", excerpt=SPAN, subcaps=[cell], origin="public")


def _inject(wb, cell, eid="E-900"):
    """A staging row registered before the rule existed."""
    wb.append("Evidence_Detail", {"E_ID": eid, "Source_Name": "Club refer-a-friend (test site)",
                                  "Source_URL": "https://test.example-club.com/refer",
                                  "Tier": "T5", "Excerpt": SPAN, "SubCap_IDs": cell})
    wb.set_scoring(cell, {"Evidence_IDs": eid,
                          "Source_URLs": "https://test.example-club.com/refer"})
    return eid


def test_retire_removes_an_uncited_staging_row_and_both_links(tmp_path):
    run, wb, cell = _cell(tmp_path)
    eid = _inject(wb, cell)
    dry = L.retire_nonproduction_evidence(wb, why="staging host is never citable evidence",
                                          actor="conducting-session", dry_run=True)
    assert dry["would_retire"] == [eid] and eid in wb.evidence_index()
    out = L.retire_nonproduction_evidence(wb, why="staging host is never citable evidence",
                                          actor="conducting-session")
    assert out["retired"] == [eid]
    wb = run.open()
    assert eid not in wb.evidence_index()
    sr = wb.scoring_row(cell)
    assert eid not in _split_ids(sr.get("Evidence_IDs"))
    assert "test.example-club.com" not in str(sr.get("Source_URLs") or "")
    assert any(g.get("Gate") == "EVIDENCE_RETIRED" for g in wb.rows("Gate_Log"))
    assert any(p.get("Step") == L.RETIRE_STEP for p in wb.rows("Provenance"))


def test_retire_keeps_a_staging_row_prose_still_cites(tmp_path):
    run, wb, cell = _cell(tmp_path)
    eid = _inject(wb, cell)
    wb.set_scoring(cell, {"Dominant_Claim": f"The club offers a referral reward ({eid})."})
    out = L.retire_nonproduction_evidence(wb, why="staging host is never citable evidence",
                                          actor="conducting-session")
    assert out["retired"] == [] and eid in out["kept_cited"]
    assert eid in run.open().evidence_index()


PROD = "https://www.example-club.com/refer"


def test_retire_names_the_repoint_repair_for_a_cited_row(tmp_path):
    run, wb, cell = _cell(tmp_path)
    eid = _inject(wb, cell)
    wb.set_scoring(cell, {"Dominant_Claim": f"The club runs a referral programme [{eid}]."})
    out = L.retire_nonproduction_evidence(run.open(), why="pre-production host is not the served site",
                                          dry_run=True)
    assert eid in out["kept_cited"]
    assert "engine.cli repoint" in out["fix"][eid]


def test_repoint_refuses_until_the_production_page_was_read(tmp_path):
    run, wb, cell = _cell(tmp_path)
    eid = _inject(wb, cell)
    with pytest.raises(L.LedgerRefusal, match="nothing in this run has read"):
        L.repoint_evidence(run.open(), eid, PROD, why="production copy of the same page", run=run)


def test_repoint_refuses_another_site_or_a_non_staging_row(tmp_path):
    run, wb, cell = _cell(tmp_path)
    eid = _inject(wb, cell)
    with pytest.raises(L.LedgerRefusal, match="not the same site"):
        L.repoint_evidence(run.open(), eid, "https://other-club.com/refer",
                           why="production copy of the same page", run=run)
    with pytest.raises(L.LedgerRefusal, match="itself pre-production"):
        L.repoint_evidence(run.open(), eid, "https://staging.example-club.com/refer",
                           why="production copy of the same page", run=run)
    with pytest.raises(L.LedgerRefusal, match="--why"):
        L.repoint_evidence(run.open(), eid, PROD, why="short", run=run)


def test_repoint_moves_a_verified_row_and_its_links(tmp_path, monkeypatch):
    from engine import fetch as F
    run, wb, cell = _cell(tmp_path)
    eid = _inject(wb, cell)
    wb.append("Subcap_Scores", {"subcap_id": cell, "score": 2.0, "evidence_ids": eid,
                                "source_urls": "https://test.example-club.com/refer"})
    pages = {PROD: "Header. " + SPAN + " Footer."}
    monkeypatch.setattr(F, "cached_text", lambda _run, url: pages.get(url))
    out = L.repoint_evidence(run.open(), eid, PROD,
                             why="production copy of the same page carries the span", run=run)
    assert out["to"] == PROD and out["cells"] == [cell]
    wb = run.open()
    assert wb.evidence_index()[eid]["Source_URL"] == PROD
    row = next(r for r in wb.scoring_rows() if r["SubCap_ID"] == cell)
    assert _split_ids(row["Source_URLs"]) == [PROD]
    sc = next(r for r in wb.rows("Subcap_Scores") if r["subcap_id"] == cell)
    assert _split_ids(sc["source_urls"]) == [PROD]
    assert any(r.get("Gate") == "EVIDENCE_REPOINTED" for r in wb.rows("Gate_Log"))
    assert any(r.get("Step") == L.REPOINT_STEP for r in wb.rows("Provenance"))


def test_repoint_refuses_a_production_page_that_says_something_else(tmp_path, monkeypatch):
    from engine import fetch as F
    run, wb, cell = _cell(tmp_path)
    eid = _inject(wb, cell)
    monkeypatch.setattr(F, "cached_text", lambda _run, url: "A different offer entirely.")
    with pytest.raises(L.LedgerRefusal, match="excerpt_not_verbatim"):
        L.repoint_evidence(run.open(), eid, PROD,
                           why="production copy of the same page carries the span", run=run)
