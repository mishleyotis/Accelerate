""""Verbatim" was a word in an error message. Now it is a check.

MEASURED. `ledger.append_evidence` checked the excerpt's LENGTH — 50-500
characters — and nothing else; the word "verbatim" appeared only in the
refusal text for a span of the wrong size. The one real verification in the
system lived in the app connector's `register_evidence`, a tool every
research agent's manifest denies. So the engine's fail-closed evidence rule
(invariant 4) was, at the write path a lane actually uses, a length check.

The fix is the fetch cache: `engine.cli fetch` already has the page's text
under the run, so the ledger compares the span against it. Three outcomes
and they are not the same:

  cached, span present    registers.
  cached, span absent     `excerpt_not_verbatim` — re-extract from the
                          source; never repair by hand.
  not cached              `excerpt_unverified` when verification is on,
                          UNLESS the caller says why (`--unverified
                          REASON`), which is recorded on the row's
                          Access_Status. Recorded, never silent.

The library default is verify_excerpts=False so the fixtures and every
in-process caller are untouched; the CLI and `memory.consolidate` pass True,
which is where a lane's writes actually go.
"""
import json

import pytest

from engine import fetch as F
from engine import ledger as L
from engine import memory as M

from fixtures import fire_volleys, new_run

URL = "https://acme.example/annual-report-2025"

PAGE = ("Acme Credit Union annual report 2025.  \n\n"
        "Alkami digital banking went live in Q3 2024 and reached 47 percent "
        "member adoption within ninety days, restated at 51 percent in the "
        "2025 report.\n"
        "The board approved a three-year core conversion programme.")

#: 50-500 characters, and genuinely in the page above.
SPAN = ("Alkami digital banking went live in Q3 2024 and reached 47 percent "
        "member adoption within ninety days")


def _cache(run, url=URL, text=PAGE):
    F.fetch_text(run, url, fetcher=lambda u: text)


def _cell(run):
    return run.open().selected_subcaps()[0]


def _register(wb, cell, excerpt, **kw):
    return L.append_evidence(
        wb, source_name="Annual Report 2025", source_url=URL, tier="T2",
        excerpt=excerpt, subcaps=[cell], published="2025-06-01", **kw)


# ── a cached page is the authority, whatever the flag says ────────────

def test_a_cached_page_refuses_a_span_it_does_not_carry(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    _cache(run)
    wb = run.open()
    with pytest.raises(L.LedgerRefusal) as e:
        _register(wb, _cell(run),
                  "Alkami digital banking went live in Q3 2024 and reached 91 "
                  "percent member adoption within thirty days")
    assert "excerpt_not_verbatim" in str(e.value)
    assert "e-extract it from the source" in str(e.value)


def test_a_cached_page_refuses_the_invented_span_even_with_verification_off(
        tmp_path):
    """Fail-closed: the page is right here. Not looking at it because a flag
    is off would make the check an opinion."""
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    _cache(run)
    with pytest.raises(L.LedgerRefusal) as e:
        _register(run.open(), _cell(run),
                  "The credit union operates a Temenos Transact core and has "
                  "completed its migration to the public cloud in full")
    assert "excerpt_not_verbatim" in str(e.value)


def test_a_verbatim_span_registers(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    _cache(run)
    eid = _register(run.open(), _cell(run), SPAN, verify_excerpts=True)
    assert eid.startswith("E")


def test_whitespace_and_case_do_not_make_a_different_span(tmp_path):
    """The comparison normalises whitespace and case and NOTHING else —
    the same normalisation `register_evidence` makes, so a span that passes
    the engine passes the connector."""
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    _cache(run)
    wobbled = "  ALKAMI digital   banking went live in Q3 2024\nand reached " \
              "47 PERCENT member adoption within ninety days  "
    eid = _register(run.open(), _cell(run), wobbled, verify_excerpts=True)
    assert eid.startswith("E")


def test_a_span_across_an_html_tag_boundary_verifies(tmp_path):
    """The inline-XBRL case, end to end: the sentence a reader sees is not a
    substring of the markup, and is a substring of the extracted text."""
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    markup = ('<p>At December 31, 2025, we had <ix:nonFraction scale="9">'
              '$1,775.6</ix:nonFraction> billion in assets under management, '
              'up from $1,444.4 billion a year earlier.</p>')
    F.fetch_text(run, URL, fetcher=lambda u: F.html_text(markup))
    span = ("At December 31, 2025, we had $1,775.6 billion in assets under "
            "management, up from $1,444.4 billion a year earlier.")
    assert span not in markup, "the fixture is not the ix case"
    assert _register(run.open(), _cell(run), span, verify_excerpts=True)


# ── an uncached URL: refused, or recorded as unverified ────────────────

def test_an_uncached_url_is_refused_when_verification_is_on(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    with pytest.raises(L.LedgerRefusal) as e:
        _register(run.open(), _cell(run), SPAN, verify_excerpts=True)
    msg = str(e.value)
    assert "excerpt_unverified" in msg
    assert "engine.cli fetch" in msg, "the refusal must name the way out"
    assert "--unverified" in msg


def test_a_reason_records_the_row_as_unverified(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    wb = run.open()
    eid = _register(wb, _cell(run), SPAN, verify_excerpts=True,
                    unverified_reason="403 from the entity's WAF; read "
                                      "through Tavily extract")
    row = [r for r in run.open().rows("Evidence_Detail") if r["E_ID"] == eid][0]
    assert str(row["Access_Status"]).startswith("UNVERIFIED: ")
    assert "403" in str(row["Access_Status"])


def test_an_empty_reason_is_not_a_reason(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    with pytest.raises(L.LedgerRefusal) as e:
        _register(run.open(), _cell(run), SPAN, verify_excerpts=True,
                  unverified_reason="   ")
    assert "excerpt_unverified" in str(e.value)


def test_an_internal_source_with_no_url_is_not_a_fetch_question(tmp_path):
    """Verification is about a URL. An internal document has none, is
    labelled origin='internal', and is refused or not on its own terms."""
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    eid = L.append_evidence(
        run.open(), source_name="Board pack Q3", source_url=None, tier="T1",
        excerpt=SPAN, subcaps=[_cell(run)], origin="internal",
        verify_excerpts=True)
    assert eid.startswith("E")


# ── the default is unchanged, so the fixtures are untouched ───────────

def test_the_library_default_is_off(tmp_path):
    """Every existing in-process caller — the fixtures, the stub, the
    handoff — registers against URLs nothing fetched. Flipping the default
    would rewrite the meaning of every test in this directory rather than
    add a check to the path a lane uses."""
    import inspect
    sig = inspect.signature(L.append_evidence)
    assert sig.parameters["verify_excerpts"].default is False
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    assert _register(run.open(), _cell(run), SPAN).startswith("E")


# ── the CLI verifies; that is where a lane writes ─────────────────────

def _cli_evidence(run, cell, excerpt, *extra):
    from engine import cli
    return cli.main(["evidence", "--run", run.run_id, "--root", str(run.root),
                     "--subcap", cell, "--source", "Annual Report 2025",
                     "--url", URL, "--tier", "T2", "--excerpt", excerpt,
                     *extra])


def test_the_cli_refuses_an_uncached_public_url(tmp_path, capsys):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    rc = _cli_evidence(run, _cell(run), SPAN)
    err = capsys.readouterr().err
    assert rc == 1
    assert "excerpt_unverified" in err and "engine.cli fetch" in err


def test_the_cli_registers_a_span_the_cache_carries(tmp_path, capsys):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    _cache(run)
    rc = _cli_evidence(run, _cell(run), SPAN)
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["e_id"].startswith("E")


def test_the_cli_unverified_flag_records_the_reason(tmp_path, capsys):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    rc = _cli_evidence(run, _cell(run), SPAN,
                       "--unverified", "403 from the entity's WAF")
    assert rc == 0
    eid = json.loads(capsys.readouterr().out)["e_id"]
    row = [r for r in run.open().rows("Evidence_Detail") if r["E_ID"] == eid][0]
    assert str(row["Access_Status"]) == "UNVERIFIED: 403 from the entity's WAF"


def test_the_cli_refuses_an_invented_span_even_with_unverified(tmp_path, capsys):
    """`--unverified` excuses a page nobody could fetch. It does not excuse
    a span contradicted by a page in hand."""
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    _cache(run)
    rc = _cli_evidence(run, _cell(run),
                       "The credit union completed its Temenos Transact core "
                       "migration to the public cloud in full during 2025",
                       "--unverified", "I would rather not fetch it")
    assert rc == 1
    assert "excerpt_not_verbatim" in capsys.readouterr().err


# ── consolidate: a WebFetch-only note is BLOCKED in place ─────────────

def _note(run, cell, excerpt, url=URL):
    M.note(run, category=cell.split(".")[0], subcap=[cell], facet="works",
           kind="evidence", source_name="Annual Report 2025", url=url,
           tier="T2", excerpt=excerpt, published="2025-06-01",
           claim="Alkami went live in Q3 2024")


def test_consolidate_blocks_a_note_whose_page_was_never_fetched(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    cell = _cell(run)
    fire_volleys(run.open(), cell)
    _note(run, cell, SPAN)
    out = M.consolidate(run, cell.split(".")[0])
    assert out["consolidated"] == 0 and out["blocked"] == 1
    assert "excerpt_unverified" in out["results"][0]["blocked"]
    body = M.memory_path(run, cell.split(".")[0]).read_text()
    assert "[BLOCKED]" in body and "excerpt_unverified" in body


def test_consolidate_registers_a_note_the_cache_verifies(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    cell = _cell(run)
    fire_volleys(run.open(), cell)
    _cache(run)
    _note(run, cell, SPAN)
    out = M.consolidate(run, cell.split(".")[0])
    assert out["blocked"] == 0 and out["consolidated"] == 1


def test_consolidate_blocks_an_invented_span(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    cell = _cell(run)
    fire_volleys(run.open(), cell)
    _cache(run)
    _note(run, cell,
          "Alkami digital banking went live in Q3 2024 and reached 91 percent "
          "member adoption within thirty days of launch")
    out = M.consolidate(run, cell.split(".")[0])
    assert out["blocked"] == 1
    assert "excerpt_not_verbatim" in out["results"][0]["blocked"]
