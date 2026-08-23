"""A citation the reader cannot open, and a quote that was never one span.

Both measured 2026-08-23 against the production API over the COMPLETE served
evidence set, which is the only way either shows up — a sample of twenty finds
the twenty that work:

    T. Rowe Price   894 items   757 with no URL (85%)   480 stitched (53%)
    Baxter (gold)   154 items     1 with no URL         0 stitched

The URLs were in the package the whole time. `01_evidence/evidence_index.json`
carries 752 items with 748 URLs; ingest re-minted every id into `E-TROW-nnn`
and dropped the column. 751 of 752 still join numerically and 747 URLs are
recoverable without researching anything.

The tests below carry the real shapes from both runs. Two of them exist
because of mistakes made writing this gate, and they are the ones worth
keeping: a stitch rule that could not fire, and a truncation rule that flagged
40% of the gold standard.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate_m_evidence_url_and_span as g  # noqa: E402

#: Verbatim from the T. Rowe drawer — three facts glued with pipes.
STITCHED = (
    "CTO Ramon Richards (joined 2023, ex-Fannie Mae CIO 24+yrs) runs "
    "technology strategy under three named pillars: modernization, "
    "artificial int | Richards on modernization: retiring legacy systems, "
    "simplifying the technology environment, new data capabilities "
    "eliminating redundancy, sc | Scaled agile delivery model applied "
    "enterprise-wide with expanded")

#: Verbatim from E-482 — a real job posting. Full of pipes, and a real quote.
POSTING = ("Platform Engineer | Solutions Engineer | GCP, AWS, Snowflake, "
           "Terraform, SQL, Python, CI/CD | Infrastructure Automation, "
           "Multi-Tenant Environments")

REAL = ("We do not lend or engage in any securities sales and trading "
        "operations, and we hold no material trading positions.")


def _row(eid="E-1", url="https://sec.gov/x.htm", excerpt=REAL):
    return {"e_id": eid, "source_url": url, "excerpt": excerpt}


# ── every served item carries a URL ──


def test_a_missing_url_is_a_breach_not_a_warning():
    rep = g.audit([_row(), _row("E-2", url=None)])
    assert rep["no_url"] == ["E-2"]
    assert rep["breaches"], "a citation nobody can open has to fail"
    assert "no URL" in rep["breaches"][0]


def test_the_breach_names_where_to_look_before_researching():
    """747 of the 757 were already in the package. A message that sends the
    producer to the web first would burn a day re-finding what it had."""
    rep = g.audit([_row("E-2", url=None)])
    assert "01_evidence/evidence_index.json" in rep["breaches"][0]


def test_a_full_set_with_urls_is_clean():
    assert not g.audit([_row(f"E-{i}") for i in range(50)])["breaches"]


@pytest.mark.parametrize("url", ["", None, "  ", "multiple", "n/a",
                                 "see source", "TBD"])
def test_a_placeholder_is_not_a_url(url):
    """Baxter's one failure is `url: "multiple"` — a note to a human, and
    unopenable. A non-empty string is not the test; a scheme is."""
    assert g.audit([_row("E-9", url=url)])["no_url"] == ["E-9"]


# ── an excerpt is ONE span ──


def test_a_stitched_excerpt_is_a_breach():
    rep = g.audit([_row("E-3", excerpt=STITCHED)])
    assert rep["stitched"] == ["E-3"]
    assert any("' | '" in b for b in rep["breaches"])


def test_the_stitch_rule_actually_fires_on_the_real_shape():
    """THE MISTAKE THIS PINS. The first version anchored on word characters
    immediately before the pipe — `[\\w]{20,}\\s\\|` — which matches nothing,
    because the text before a pipe is prose and prose contains spaces. It
    reported 0 stitched on a set with 480 and looked like a clean bill of
    health. A check that cannot fire is worse than no check at all."""
    assert g._is_stitched(STITCHED) is True


def test_prose_that_merely_contains_pipes_is_not_stitched():
    """The negative control, and it is a real row. E-482's excerpt is a job
    posting: verbatim, and full of pipes."""
    assert g._is_stitched(POSTING) is False
    assert not g.audit([_row("E-482", excerpt=POSTING)])["stitched"]


def test_one_short_fragment_beside_a_long_one_is_not_stitched():
    assert g._is_stitched("A very long and continuous sentence of prose "
                          "that runs on | ok") is False


def test_an_ordinary_quote_is_never_stitched():
    assert g._is_stitched(REAL) is False


def test_the_gold_standard_would_pass_the_span_rule():
    """Baxter has 0 stitched of 154. If this rule ever starts flagging the
    exemplar, the rule is wrong — that is how the truncation check that used
    to live here was caught, having flagged 61 of Baxter's 154."""
    baxter_like = [_row(f"E-BCU-{i}", excerpt=REAL) for i in range(154)]
    assert g.audit(baxter_like)["stitched"] == []


# ── Explorium: honest as an origin, dishonest as a citation ──


def test_a_bare_hostname_warns_and_does_not_block():
    """18 T. Rowe items and 15 Baxter items cite `https://<entity>.com` with
    no path — Vibe-Prospecting technographic scans, which have no document
    behind them. Blocking would refuse a real observation; passing silently
    points the reader at a home page as though the claim were on it."""
    rep = g.audit([_row("E-002", url="https://troweprice.com")])
    assert rep["bare_host"] == ["E-002"]
    assert not rep["breaches"]
    assert any("technographic scan" in w for w in rep["warnings"])


def test_a_url_with_a_real_path_is_not_a_bare_host():
    rep = g.audit([_row("E-083",
                        url="https://files.brokercheck.finra.org/firm/firm_8348.pdf")])
    assert rep["bare_host"] == []
    assert not rep["warnings"]


# ── the reader shapes the gate has to accept ──


@pytest.mark.parametrize("payload", [
    [{"e_id": "E-1", "source_url": "https://a/b", "excerpt": REAL}],
    {"items": [{"e_id": "E-1", "source_url": "https://a/b", "excerpt": REAL}]},
    {"found": [{"e_id": "E-1", "source_url": "https://a/b", "excerpt": REAL}]},
    {"data": {"evidence": [{"e_id": "E-1", "url": "https://a/b",
                            "excerpt": REAL}]}},
])
def test_every_served_envelope_shape_is_readable(payload):
    """The API returns `items`, the connector returns `found`, and a staged
    payload nests under `data.evidence`. A gate that silently reads zero rows
    from one of them reports a clean run for a broken one."""
    assert g._rows_from(payload), "read zero rows from a populated envelope"


def test_an_empty_set_is_not_silently_clean():
    """Nothing to audit must not look like nothing wrong — the caller has to
    be able to tell the two apart."""
    assert g.audit([])["total"] == 0
