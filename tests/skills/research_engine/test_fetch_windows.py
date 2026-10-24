"""Windows out of a page, instead of the page into the context.

THE MEASUREMENT. A research lane that wants a 50-500 character excerpt
WebFetches the whole page to find it. That page then sits in the lane's
context and is re-read on every later turn: 76% of the measured six-cell
lane bill was cache reads — 24.45M cache-read tokens, $4.89 of $6.45. One
fetch is 5-40K tokens re-read every turn after it; three 240-character
windows are ~200 tokens, read once.

So `engine.fetch` fetches OUT of process, caches the extracted text under
the run, and hands back only the spans that answer the query. The cache is
also what makes the excerpt VERIFIABLE at the engine (test_excerpt_
verification.py): until this existed the engine checked an excerpt's LENGTH
and nothing else, and the word "verbatim" appeared only in the error text.

Nothing here reaches a model, and `windows` reaches nothing at all
(invariant 1): extraction and ranking are stdlib, deterministic and local.
"""
import importlib.util
import io
import json
import socket
import sys
from pathlib import Path

import pytest

from engine import fetch as F

from fixtures import new_run


# ── the extractors, on the two cases that were MEASURED ────────────────

#: MEM-0070, measured 2026-08-15: the span a producer verified by hand in
#: the fetched bytes, that `register_evidence` still called not-verbatim
#: because a PDF was decoded as UTF-8.
PDF_SPAN = ("Your Account instructions must be either oral (but not left on "
            "voicemail) or in writing (but not electronically).")

#: Measured 2026-08-22 on every T. Rowe Price 10-K: 0 of 5 excerpts matched
#: the raw bytes, 5 of 5 match the extracted text. A modern filing is
#: inline-XBRL — the sentence a reader sees is not a substring of the markup.
IXBRL = ('<html><body><p>At December 31, 2025, we had '
         '<ix:nonFraction contextRef="c1" name="us-gaap:AssetsUnderManagement" '
         'scale="9" unitRef="usd">$1,775.6</ix:nonFraction> billion in assets '
         'under management.</p></body></html>')
IXBRL_SENTENCE = ("At December 31, 2025, we had $1,775.6 billion in assets "
                  "under management.")


def _make_pdf(text: str) -> bytes:
    """A real PDF, built here rather than committed — a fixture binary
    nobody can read is a fixture nobody can check."""
    from pypdf import PdfWriter
    from pypdf.generic import (ArrayObject, DecodedStreamObject,
                               DictionaryObject, NameObject, NumberObject)

    def esc(s):
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    page = writer.pages[0]
    content = DecodedStreamObject()
    lines = "\n".join(f"({esc(l)}) Tj 0 -14 Td" for l in text.split("\n"))
    content.set_data(f"BT /F1 10 Tf 40 740 Td\n{lines}\nET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(content)
    font = DictionaryObject()
    font.update({NameObject("/Type"): NameObject("/Font"),
                 NameObject("/Subtype"): NameObject("/Type1"),
                 NameObject("/BaseFont"): NameObject("/Helvetica")})
    res = DictionaryObject()
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = writer._add_object(font)
    res[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = res
    page[NameObject("/MediaBox")] = ArrayObject(
        [NumberObject(0), NumberObject(0), NumberObject(612), NumberObject(792)])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_a_pdf_extracts_to_prose():
    pytest.importorskip("pypdf")
    raw = _make_pdf(PDF_SPAN)
    assert raw[:5] == b"%PDF-", "the fixture is not a PDF"
    out = F.pdf_text(raw)
    assert out and "voicemail" in out, f"extraction lost the prose: {out!r}"


def test_a_scanned_pdf_is_unreachable_not_empty():
    """None says unreachable, which is true; "" would blame the excerpt for
    the document having no text layer."""
    pytest.importorskip("pypdf")
    assert F.pdf_text(_make_pdf("   ")) is None
    assert F.pdf_text(b"not a pdf at all") is None


def test_inline_xbrl_extracts_to_the_sentence_a_reader_sees():
    assert IXBRL_SENTENCE not in IXBRL, "the fixture is not the ix case"
    assert IXBRL_SENTENCE in " ".join(F.html_text(IXBRL).split())


def test_inline_tags_close_up_and_block_tags_become_a_space():
    """Getting this backwards silently corrupts every comparison."""
    assert "Financial" in F.html_text("<b>Fin</b>ancial")
    out = F.html_text("<td>alpha</td><td>beta</td>")
    assert "alphabeta" not in out and "alpha" in out and "beta" in out


def test_script_and_style_are_not_prose():
    out = F.html_text("<style>p{color:red}</style><script>x=1</script>"
                      "<p>the annual report</p>")
    assert "color" not in out and "x=1" not in out
    assert "the annual report" in out


# ── the copy cannot drift from the connector's ────────────────────────

def _connector_fetching():
    """The app connector's own extractors, imported BY PATH — the plugin is
    packaged standalone and the engine imports nothing from `apps/`, so the
    equality is asserted here rather than bought with an import."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        p = parent / "apps" / "mcp" / "dma_mcp" / "fetching.py"
        if p.is_file():
            spec = importlib.util.spec_from_file_location("_conn_fetching", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


#: Markup shapes that have each cost a refusal or could: the ix filing, the
#: inline/block boundary, entities, comments, a table, an option list.
_CORPUS = [
    IXBRL,
    "<b>Fin</b>ancial <i>services</i>",
    "<td>alpha</td><td>beta</td><td>gamma</td>",
    "<p>AT&amp;T &lt;the carrier&gt; &#8212; 2025</p>",
    "<!-- a comment --><div>after the comment</div>",
    "<ul><li>one</li><li>two</li></ul>",
    "<select><option>Retail</option><option>Commercial</option></select>",
    "<head><title>t</title></head><body><h1>Heading</h1><p>Body.</p></body>",
    "<pre>  spaced   text  </pre><blockquote>quoted</blockquote>",
    "plain text with no markup at all",
]


def test_the_extractor_agrees_with_the_connectors():
    conn = _connector_fetching()
    if conn is None:
        pytest.skip("the app connector is not in this tree")
    for markup in _CORPUS:
        assert F.html_text(markup) == conn._html_text(markup), \
            f"the copy has drifted from the connector's on {markup[:60]!r}"


def test_the_pdf_extractor_agrees_with_the_connectors():
    pytest.importorskip("pypdf")
    conn = _connector_fetching()
    if conn is None:
        pytest.skip("the app connector is not in this tree")
    raw = _make_pdf(PDF_SPAN)
    assert F.pdf_text(raw) == conn._pdf_text(raw)


def test_the_error_describer_agrees_with_the_connectors():
    """Each branch names a DIFFERENT next move, which is why it is copied
    verbatim rather than collapsed to "unreachable"."""
    conn = _connector_fetching()
    if conn is None:
        pytest.skip("the app connector is not in this tree")
    import socket as _socket
    import urllib.error
    url = "https://acme.example/report"
    for exc in (urllib.error.HTTPError(url, 403, "Forbidden", None, None),
                urllib.error.HTTPError(url, 404, "Not Found", None, None),
                urllib.error.HTTPError(url, 429, "Too Many", None, None),
                urllib.error.URLError(_socket.gaierror("no such host")),
                urllib.error.URLError(TimeoutError())):
        assert F.describe_error(exc, url) == conn._describe(exc, url)


# ── windows: deterministic, local, centred on the densest hit ──────────

def _page(lead: str, hot: str, tail: str) -> str:
    return lead + " " + hot + " " + tail


def test_the_window_is_centred_on_the_densest_run_of_query_terms():
    noise = ("The credit union publishes a quarterly newsletter. " * 40)
    hot = ("Alkami digital banking went live in Q3 2024 and reached 47 "
           "percent member adoption within ninety days.")
    text = _page(noise, hot, noise)
    out = F.windows(text, "Alkami digital banking adoption")
    assert out, "no window for a query the page answers"
    first = out[0]
    assert "Alkami digital banking" in first["text"]
    assert "adoption" in first["text"]
    assert first["hits"] >= 3


def test_windows_are_deterministic():
    text = ("core conversion " * 30) + " the core banking conversion to " \
           "Fiserv DNA completed in 2025 " + ("core conversion " * 30)
    a = F.windows(text, "core banking conversion Fiserv")
    b = F.windows(text, "core banking conversion Fiserv")
    assert a == b, "two identical calls disagreed"


def test_windows_do_not_overlap_and_quote_the_text_exactly():
    hot = "Fiserv DNA core conversion completed in 2025. "
    text = ("filler sentence about members. " * 20 + hot) * 3
    out = F.windows(text, "Fiserv DNA core conversion", window=120, max_windows=3)
    assert len(out) == 3
    for w in out:
        assert text[w["start"]:w["end"]] == w["text"], \
            "the window does not quote the text it points at"
    spans = sorted((w["start"], w["end"]) for w in out)
    for (_, e), (s, _) in zip(spans, spans[1:]):
        assert e <= s, f"windows overlap: {spans}"


def test_at_most_max_windows_come_back():
    text = "Fiserv DNA conversion. " * 200
    assert len(F.windows(text, "Fiserv DNA conversion", max_windows=2)) == 2


def test_a_query_the_page_does_not_answer_gets_no_window():
    """Silence is the honest answer. A window invented around character zero
    would read as a hit and get quoted as one."""
    text = "The credit union publishes a quarterly newsletter. " * 20
    assert F.windows(text, "Temenos Transact core migration") == []


def test_an_empty_page_or_query_is_not_an_error():
    assert F.windows("", "anything") == []
    assert F.windows("some text", "") == []


def test_windows_touches_no_network_and_no_model(monkeypatch):
    """Invariant 1: the serving path never calls a model, and this ranking
    is stdlib arithmetic. Any socket at all is a bug."""
    def boom(*a, **k):
        raise AssertionError("windows() opened a socket")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    text = "Alkami digital banking adoption reached 47 percent. " * 30
    assert F.windows(text, "Alkami adoption")


def test_the_module_names_no_model():
    src = Path(F.__file__).read_text()
    for word in ("anthropic", "openai", "embedding", "completion(",
                 "claude-", "llm"):
        assert word not in src.lower(), f"{word!r} is in a deterministic module"


# ── the cache: successes kept, failures never ──────────────────────────

def _fetcher(text):
    return lambda url: text


def test_a_success_is_cached_and_the_second_read_is_free(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    url = "https://acme.example/annual-report"
    first = F.fetch_text(run, url, fetcher=_fetcher("Alkami went live in 2024."))
    assert first["error"] is None and first["from_cache"] is False
    assert first["sha256"] and len(first["sha256"]) == 64

    def never(url):
        raise AssertionError("the second read went back to the network")

    second = F.fetch_text(run, url, fetcher=never)
    assert second["from_cache"] is True
    assert second["text"] == first["text"] and second["sha256"] == first["sha256"]
    assert F.cached_text(run, url) == first["text"]


def test_a_failure_is_never_cached(tmp_path):
    """MEM-0072 was a 403 from an entity's own domain — transient and
    WAF-shaped. Freezing it into a cache turns a momentary block into a
    permanent one and makes the entity look like it has no website."""
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    url = "https://acme.example/blocked"

    def refuses(url):
        return None

    out = F.fetch_text(run, url, fetcher=refuses)
    assert out["text"] is None and out["error"]
    assert F.cached_text(run, url) is None
    assert list(F.cache_dir(run).glob("*")) == [] or \
        not any(p.suffix in (".txt", ".json") for p in F.cache_dir(run).glob("*"))

    ok = F.fetch_text(run, url, fetcher=_fetcher("it answered this time."))
    assert ok["text"] == "it answered this time." and ok["error"] is None


def test_the_fetcher_raising_is_described_not_swallowed(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    import urllib.error

    def blows_up(url):
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)

    out = F.fetch_text(run, "https://acme.example/waf", fetcher=blows_up)
    assert out["text"] is None
    assert "403" in out["error"] and "acme.example" in out["error"]


def test_the_cache_key_is_the_normalised_url(tmp_path):
    """One URL, one identity: a tracking parameter does not buy a second
    fetch of the same document."""
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    F.fetch_text(run, "https://acme.example/ar?utm_source=x",
                 fetcher=_fetcher("the annual report text"))
    assert F.cached_text(run, "https://www.acme.example/ar") == \
        "the annual report text"


def test_the_sidecar_records_what_was_fetched(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    url = "https://acme.example/ar"
    out = F.fetch_text(run, url, fetcher=_fetcher("a" * 120))
    meta = json.loads(next(F.cache_dir(run).glob("*.json")).read_text())
    assert meta["url"] == url and meta["chars"] == 120
    assert meta["sha256"] == out["sha256"] and meta["fetched_at"]


def test_the_cache_lives_under_the_runs_qa_dir(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    assert F.cache_dir(run) == run.qa_dir / "fetch_cache"


# ── the CLI prints windows and a hash, never the page ──────────────────

#: The canary sits at the far end of the page from the answering span, so
#: "did the page leak" is a question about the whole document and not about
#: the filler a legitimate window is bound to touch.
_CANARY = "The branch on Elm Street reopened after refurbishment in May. "
_BIG = (_CANARY
        + "The credit union publishes a quarterly newsletter for members. " * 470
        + "Alkami digital banking went live in Q3 2024 and reached 47 percent "
          "member adoption within ninety days. "
        + "The credit union publishes a quarterly newsletter for members. " * 10)


def _cli(run, *args):
    from engine import cli
    return cli.main(["fetch", "--run", run.run_id, "--root", str(run.root),
                     *args])


def test_the_cli_prints_windows_and_a_hash_and_never_the_page(
        tmp_path, capsys, monkeypatch):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    assert len(_BIG) > 30_000, "the fixture page is not big enough to matter"
    monkeypatch.setattr(F, "_http_text", _fetcher(_BIG))
    rc = _cli(run, "--url", "https://acme.example/ar",
              "--query", "Alkami digital banking adoption")
    out = capsys.readouterr().out
    assert rc == 0
    assert len(out) < 2_000, \
        f"the CLI put {len(out)} chars of page into the context"
    assert "Alkami digital banking" in out, "the answering span is missing"
    assert F.sha256(_BIG) in out, "the hash that ties the excerpt to the page"
    assert _CANARY.strip() not in out, "the page leaked through"


def test_the_cli_json_form_is_the_same_answer(tmp_path, capsys, monkeypatch):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    monkeypatch.setattr(F, "_http_text", _fetcher(_BIG))
    rc = _cli(run, "--url", "https://acme.example/ar", "--json",
              "--query", "Alkami digital banking adoption")
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["sha256"] == F.sha256(_BIG)
    assert payload["chars"] == len(_BIG)
    assert payload["windows"] and "Alkami" in payload["windows"][0]["text"]
    assert "text" not in payload, "the whole page is in the JSON"


def test_the_cli_reports_a_failure_with_its_reason(tmp_path, capsys, monkeypatch):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    monkeypatch.setattr(F, "_http_text", lambda url: None)
    rc = _cli(run, "--url", "https://acme.example/x", "--query", "anything")
    assert rc == 1
    assert "acme.example" in (capsys.readouterr().err or "")


def test_via_text_caches_a_connectors_own_extract(tmp_path, capsys, monkeypatch):
    """A servicing actor reads a page through Tavily extract. `--via-text -`
    puts that text in the same cache under the same URL, so the ledger can
    verify an excerpt taken from it exactly as it verifies a fetched one —
    and no second fetch is bought."""
    run = new_run(tmp_path, n=2, prelim=False, folder=False)

    def never(url):
        raise AssertionError("--via-text went to the network")

    monkeypatch.setattr(F, "_http_text", never)
    monkeypatch.setattr(sys, "stdin", io.StringIO(
        "Alkami digital banking went live in Q3 2024 and member adoption "
        "reached 47 percent within ninety days."))
    rc = _cli(run, "--url", "https://acme.example/ar", "--via-text", "-",
              "--query", "Alkami adoption")
    out = capsys.readouterr().out
    assert rc == 0 and "Alkami" in out
    assert "47 percent" in F.cached_text(run, "https://acme.example/ar")


def test_the_window_size_and_count_are_arguments(tmp_path, capsys, monkeypatch):
    run = new_run(tmp_path, n=2, prelim=False, folder=False)
    monkeypatch.setattr(F, "_http_text", _fetcher(
        "Fiserv DNA core conversion completed. " * 100))
    _cli(run, "--url", "https://acme.example/x", "--json", "--window", "80",
         "--max", "1", "--query", "Fiserv DNA conversion")
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["windows"]) == 1
    assert len(payload["windows"][0]["text"]) <= 120
