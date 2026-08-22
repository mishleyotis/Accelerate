"""The two reasons a true citation was refused: the header, and the container.

Both found 2026-08-22 trying to put a five-year financial trajectory on the
T. Rowe Price overview. The producer had already searched correctly and named
the right documents; `register_evidence` refused all five points, twice, for
two different reasons — and each refusal reads exactly like the producer
having invented the citation.

  1. `url_unreachable: HTTP 403 from www.sec.gov`. EDGAR requires an
     automated client to identify itself and refuses browser-spoofed traffic.
     The connector sends a browser UA to get past entity WAFs, so the header
     that makes every credit union's site answer is the one that makes the SEC
     refuse. Net effect: NO US public filer's own annual report could be cited,
     which is the primary source for the financial trajectory on every
     public-company assessment this product produces.

  2. `excerpt_not_verbatim`. A modern filing is inline-XBRL, so every tagged
     figure is wrapped and the sentence a reader sees is not a substring of
     the bytes. 0 of 5 excerpts matched the raw markup; 5 of 5 match the text.

The network tests are marked and skip when EDGAR is unreachable — but they
are real fetches on purpose. Both defects were invisible to a mocked fetcher:
one lives in a header a mock does not send, the other in bytes a fixture does
not have.
"""
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp.fetching import (_BROWSER_UA, _DECLARED_UA,      # noqa: E402
                              _fetch, _html_text, _ua_for)


def _norm(t):
    """What `register.py` compares with — whitespace and case, nothing else."""
    return re.sub(r"\s+", " ", t or "").strip().lower()


# ── which User-Agent a host gets ──


@pytest.mark.parametrize("url", [
    "https://www.sec.gov/Archives/edgar/data/1113169/000162828026008002/trow-20251231.htm",
    "https://sec.gov/cgi-bin/browse-edgar?action=getcompany",
    "https://data.sec.gov/api/xbrl/companyconcept/CIK0001113169.json",
    "https://efts.sec.gov/LATEST/search-index?q=test",
])
def test_sec_hosts_get_the_declaring_agent(url):
    assert _ua_for(url) == _DECLARED_UA


@pytest.mark.parametrize("url", [
    "https://www.bcu.org/about",
    "https://www.troweprice.com/retirement-plan-services/",
    "https://www.fool.com/earnings/call-transcripts/2026/08/07/x",
])
def test_everyone_else_keeps_the_browser_agent(url):
    assert _ua_for(url) == _BROWSER_UA


def test_a_lookalike_domain_is_not_treated_as_the_sec():
    """Suffix matching that forgot the dot would hand the declaring agent to
    anyone who registered `notsec.gov`."""
    assert _ua_for("https://notsec.gov/filings") == _BROWSER_UA
    assert _ua_for("https://sec.gov.evil.example/x") == _BROWSER_UA


def test_the_declared_agent_carries_no_personal_address():
    """EDGAR asks for a contact, not for a person. A header is broadcast to a
    third party on every fetch, so it names the tool and a published URL."""
    assert "@" not in _DECLARED_UA
    assert _DECLARED_UA.startswith("Zennify DMA-Insights/")
    assert "zennify.com" in _DECLARED_UA


# ── markup is not prose ──


def test_a_tagged_figure_no_longer_breaks_the_sentence():
    """The exact inline-XBRL shape that refused all five 10-K excerpts."""
    markup = ('<p>At December 31, 2025, we had '
              '<ix:nonFraction contextRef="c-1" unitRef="usd" scale="6">'
              '$1,775.6</ix:nonFraction> billion in assets under management.</p>')
    assert ("at december 31, 2025, we had $1,775.6 billion in assets under "
            "management." in _norm(_html_text(markup)))


def test_an_inline_tag_does_not_split_a_word():
    assert "financial" in _norm(_html_text("<b>Fin</b>ancial"))


def test_a_block_tag_does_not_join_two_cells():
    """The mirror error. Closing up block tags too would silently glue every
    table into one run-on token and quietly corrupt every comparison."""
    assert _norm(_html_text("<td>1,687.8</td><td>1,274.7</td>")) == "1,687.8 1,274.7"


def test_entities_become_the_characters_they_stand_for():
    assert _norm(_html_text("<p>AT&amp;T&nbsp;said &quot;yes&quot;</p>")) == 'at&t said "yes"'


def test_script_and_style_bodies_are_dropped_not_read_as_prose():
    got = _norm(_html_text(
        "<style>.x{color:red}</style><script>var s='we had $9 billion';</script>"
        "<p>The real sentence.</p>"))
    assert got == "the real sentence."


def test_a_comment_is_not_prose():
    assert _norm(_html_text("<p>Kept.</p><!-- we had $9 billion -->")) == "kept."


# ── the real thing ──


def _edgar_reachable():
    try:
        req = urllib.request.Request(
            "https://www.sec.gov/Archives/edgar/data/1113169/"
            "000162828026008002/trow-20251231.htm",
            headers={"User-Agent": _DECLARED_UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except Exception:                                  # noqa: BLE001
        return False


NET = pytest.mark.skipif(not _edgar_reachable(),
                         reason="EDGAR not reachable from this runner")

#: One sentence per year, as filed. These are the five points the T. Rowe
#: Price trajectory needed and could not cite.
FILINGS = [
    ("https://www.sec.gov/Archives/edgar/data/1113169/000111316922000005/trow-20211231.htm",
     "At December 31, 2021, we had $1,687.8 billion in assets under management,"),
    ("https://www.sec.gov/Archives/edgar/data/1113169/000111316923000007/trow-20221231.htm",
     "At December 31, 2022, we had $1,274.7 billion in assets under management,"),
    ("https://www.sec.gov/Archives/edgar/data/1113169/000111316924000007/trow-20231231.htm",
     "At December 31, 2023, we had $1,444.5 billion in assets under management, "
     "an increase of $169.8 billion from 2022."),
    ("https://www.sec.gov/Archives/edgar/data/1113169/000111316925000007/trow-20241231.htm",
     "At December 31, 2024, we had $1,606.6 billion in assets under management, "
     "an increase of $162.1 billion from the end of 2023."),
    ("https://www.sec.gov/Archives/edgar/data/1113169/000162828026008002/trow-20251231.htm",
     "At December 31, 2025, we had $1,775.6 billion in assets under management, "
     "an increase of $169.0 billion from the end of 2024."),
]


@NET
@pytest.mark.parametrize("url,excerpt", FILINGS)
def test_a_public_filers_own_annual_report_can_be_cited(url, excerpt):
    got = _fetch(url)
    assert got is not None, (
        f"EDGAR refused {url} — {getattr(_fetch, 'last_error', None)}")
    assert _norm(excerpt) in _norm(got), (
        "the sentence is on the page and did not survive to the comparison")


@NET
def test_the_browser_agent_is_still_what_edgar_refuses():
    """The negative control. Without it this suite would keep passing if the
    declaring agent were quietly dropped and EDGAR later relaxed its policy —
    and we would not know which of the two was true."""
    req = urllib.request.Request(FILINGS[-1][0], headers={"User-Agent": _BROWSER_UA})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=30)
    assert e.value.code == 403
