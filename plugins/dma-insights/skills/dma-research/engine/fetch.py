#!/usr/bin/env python3
"""Read a page OUT of process and bring back only the spans that answer.

WHY THIS EXISTS, MEASURED. A research lane that wants a 50-500 character
excerpt WebFetches the whole page to find it. The page then sits in the
lane's context and is re-read on every later turn: on the measured six-cell
lane, 76% of the bill was cache reads — 24.45M cache-read tokens, $4.89 of
$6.45. One fetch is 5-40K tokens re-read every turn after it; three
240-character windows are ~200 tokens, read once. That is the largest single
lever on the cache-read line.

AND IT IS THE ONLY ONE THAT MAKES AN EXCERPT VERIFIABLE AT THE ENGINE.
`ledger.append_evidence` checked the excerpt's LENGTH and nothing else — the
word "verbatim" appeared only in the refusal text for a span of the wrong
size. The one real check lived in the app connector's `register_evidence`, a
tool every research agent's manifest denies. Once the extracted text is on
disk under the run, the ledger can compare the span against it, so
`engine.cli fetch` both saves the tokens and closes invariant 4 at the write
path a lane actually uses.

NO MODEL, NO REQUEST-TIME INFERENCE (invariant 1). Extraction is stdlib
(plus optional pypdf, already a declared dependency); the ranking in
`windows` is term arithmetic over the run's own tokeniser. `windows` touches
nothing at all — no network, no disk.

WHY `html_text` / `pdf_text` / `describe_error` ARE COPIED, NOT IMPORTED.
They are the app connector's (`apps/mcp/dma_mcp/fetching.py`), and this
plugin is packaged standalone — a trigger-fired container has the plugin and
no checkout, so an import from `apps/` is an import that is not there. The
copy is pinned against the original by
`tests/skills/research_engine/test_fetch_windows.py::
test_the_extractor_agrees_with_the_connectors`, which imports the connector
by path and skips when it is absent, so the two cannot drift silently. Both
sides must keep extracting the same prose, because an excerpt verified here
is registered there.

    python3 -m engine.cli fetch --run R --url U --query '<the DQ text>'
    python3 -m engine.cli fetch --run R --url U --query '…' --json
    <extract> | python3 -m engine.cli fetch --run R --url U --via-text - --query '…'
"""
from __future__ import annotations

# Runnable both ways. `python3 -m engine.<mod>` is the documented invocation,
# but every audit and every operator reaches for `python3 <path> --help`
# first, and a relative import dies there.
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import datetime as _dt
import hashlib
import json
import re
from bisect import bisect_left
from pathlib import Path

from .retrieval import _TOKEN, _tokens, normalise_url

#: Under the run's QA directory, beside every other artefact a gate reads.
#: Per RUN, not per process: the point is that the text survives the turn
#: that fetched it, so a later `engine.cli evidence` can be checked against
#: it — a process-lifetime cache would verify nothing across a lane's turns.
CACHE_DIRNAME = "fetch_cache"

#: How wide a window is, and how many come back. 240 chars is twice the
#: EXCERPT_MIN of 50 and half the EXCERPT_MAX of 500: wide enough that the
#: registrable span is inside one window, narrow enough that three of them
#: are ~200 tokens.
DEFAULT_WINDOW = 240
DEFAULT_MAX_WINDOWS = 3


# ── extraction: copied from the connector, pinned by an equality test ────

def pdf_text(raw: bytes) -> str | None:
    """The text of a PDF, or None if it has none to give.

    MEM-0070, measured 2026-08-15 on the second client. Its own WAF answers
    403 to every HTML path while `/docs/*.pdf` returns 200, so the firm's
    substantive disclosures — client agreement, statement guides, every
    career posting — are reachable ONLY as PDFs. A producer registering from
    them scored 0 of 3; the same producer scored 13 of 13 on HTML. The span
    was verifiably present in the fetched bytes and `register_evidence`
    still answered `excerpt_not_verbatim`, because the fetcher decoded a
    binary container as UTF-8 and compared prose against mojibake.

    Extraction only. No fuzzy matching, no repair: the verbatim comparison
    downstream is unchanged and still normalises nothing but whitespace and
    case. Ligatures are folded because they are an ENCODING difference — a
    PDF stores "ﬁ" for the same two letters the source page shows — and
    folding them compares the same characters rather than loosening what
    counts as the same text.
    """
    import io
    try:
        from pypdf import PdfReader
    except Exception:                                       # noqa: BLE001
        return None
    try:
        pages = PdfReader(io.BytesIO(raw)).pages
        text = "\n".join((p.extract_text() or "") for p in pages)
    except Exception:                                       # noqa: BLE001
        return None
    if not text.strip():
        # A scanned PDF is an image. Returning "" here would read as a
        # fetched-but-non-matching artefact, which blames the excerpt for the
        # document's lack of a text layer. None says unreachable, which is true.
        return None
    for lig, plain in (("ﬀ", "ff"), ("ﬁ", "fi"), ("ﬂ", "fl"),
                       ("ﬃ", "ffi"), ("ﬄ", "ffl"), ("ﬅ", "st"),
                       ("’", "'"), ("‘", "'"),
                       ("“", '"'), ("”", '"')):
        text = text.replace(lig, plain)
    return text


def html_text(markup: str) -> str:
    """The prose of an HTML document, so an excerpt is compared against prose.

    The same defect `pdf_text` fixed, one container along. A modern filing is
    inline-XBRL: every tagged figure is wrapped, so

        At December 31, 2025, we had <ix:nonFraction ...>$1,775.6</ix:nonFraction> billion

    contains the sentence a reader sees and does NOT contain it as a
    substring. Measured 2026-08-22: 0 of 5 T. Rowe Price 10-K excerpts
    matched the raw bytes; 5 of 5 match the extracted text.

    INLINE TAGS CLOSE UP, BLOCK TAGS BECOME A SPACE. `<b>Fin</b>ancial` is
    one word and must not become two; `<td>a</td><td>b</td>` is two and must
    not become one. Getting that backwards silently corrupts every
    comparison.
    """
    import html as _html
    s = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", markup)
    s = re.sub(r"(?is)<!--.*?-->", " ", s)
    s = re.sub(r"(?i)</?(p|div|br|hr|tr|td|th|li|ul|ol|dl|dd|dt|h[1-6]|table|"
               r"thead|tbody|tfoot|section|article|header|footer|nav|aside|"
               r"blockquote|pre|figure|figcaption|option)\b[^>]*>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return _html.unescape(s)


def describe_error(exc: BaseException, url: str) -> str:
    """The failure, in words a producer can act on.

    Each branch names a DIFFERENT next move, which is the whole reason the
    distinction is worth carrying: a 403 means find another source for the
    same fact, NXDOMAIN means the URL is wrong, and a timeout means try
    again. "unreachable" means all three and therefore none of them — it was
    an open BLOCKER for two clients because nobody could tell which.
    """
    import socket
    import ssl
    import urllib.error

    host = ""
    m = re.match(r"^[a-z]+://([^/:?#]+)", url or "", flags=re.I)
    if m:
        host = m.group(1)
    if isinstance(exc, urllib.error.HTTPError):
        server = (exc.headers.get("Server") or "").strip() if exc.headers else ""
        via = f" (served by {server})" if server else ""
        if exc.code in (401, 403):
            return (f"HTTP {exc.code} from {host}{via} — the host answered and "
                    "refused. Usually a bot filter rather than the page being "
                    "absent: the fact is likely still there, so cite it from "
                    "another source rather than recording an absence")
        if exc.code == 404:
            return (f"HTTP 404 from {host} — the host answered and does not "
                    "have this path. The URL is wrong or the page is gone; "
                    "an absence here is about the URL, not the capability")
        if exc.code == 429:
            return f"HTTP 429 from {host} — rate limited; retry later"
        return f"HTTP {exc.code} from {host}{via}"
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, socket.gaierror):
            return (f"DNS lookup failed for {host} — no such host. The URL is "
                    "wrong or the domain is gone; nothing about the entity's "
                    "capability follows from this")
        if isinstance(reason, ssl.SSLError):
            return f"TLS failure talking to {host}: {type(reason).__name__}"
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return f"timed out connecting to {host} after 30s"
        return f"could not connect to {host}: {reason}"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return f"timed out reading from {host} after 30s"
    return f"{type(exc).__name__} fetching {host}: {str(exc)[:120]}"


#: The browser-shaped default. Bare python-urllib is WAF-blocked by most
#: entity sites — bcu.org rejected the first prod registration.
_BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

#: What we send to hosts that ASK to be told who is calling. SEC EDGAR's
#: access policy requires an automated client to identify itself and answers
#: 403 to browser-spoofed traffic — measured 2026-08-22 against every
#: T. Rowe Price 10-K: 403 with the browser UA, 200 with this one.
_DECLARED_UA = "Zennify DMA-Insights/1.0 (+https://www.zennify.com)"

#: Suffix-matched, so `data.sec.gov` is covered and `notsec.gov` is not.
_DECLARE_HOSTS = ("sec.gov",)


def _ua_for(url: str) -> str:
    m = re.match(r"^[a-z]+://([^/:?#]+)", url or "", flags=re.I)
    host = (m.group(1) if m else "").lower().rstrip(".")
    for suffix in _DECLARE_HOSTS:
        if host == suffix or host.endswith("." + suffix):
            return _DECLARED_UA
    return _BROWSER_UA


def _http_text(url: str) -> str | None:
    """GET the URL, hand back TEXT, None on failure with the reason recorded.

    Neither PDFs nor HTML come back as their container: what the caller
    compares an excerpt against is always prose. MAGIC BYTES DECIDE — a
    filing served as application/octet-stream is still a PDF, and a `.pdf`
    path that 200s with an HTML error page is still HTML.

    The reason lives on the function (`_http_text.last_error`) rather than in
    the return, so a caller may substitute any plain `fetcher(url) -> str |
    None` and the contract still holds.
    """
    import urllib.request

    _http_text.last_error = None
    _http_text.last_content_type = ""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _ua_for(url),
            # `*/*` last, but application/pdf named explicitly: a server that
            # content-negotiates will not offer a PDF to a client whose
            # Accept header only ever asked for HTML.
            "Accept": ("text/html,application/xhtml+xml,application/pdf,"
                       "application/xml;q=0.9,*/*;q=0.8"),
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(20_000_000)
            ctype = (r.headers.get("Content-Type") or "").lower()
    except Exception as exc:                                # noqa: BLE001
        # WHY it failed, not merely THAT it failed.
        _http_text.last_error = describe_error(exc, url)
        return None
    _http_text.last_content_type = ctype
    if raw[:5] == b"%PDF-" or "application/pdf" in ctype:
        text = pdf_text(raw)
        if text is None:
            _http_text.last_error = (
                f"the PDF at {url} has no text layer (a scan, or pypdf is not "
                f"installed) — it is an image, not a document this can quote")
        return text
    return html_text(raw.decode("utf-8", "replace"))


_http_text.last_error = None
_http_text.last_content_type = ""


# ── the run's cache: successes kept, failures never ──────────────────────

def cache_dir(run) -> Path:
    """`<run>/07_qa/fetch_cache`. Under the run because that is what makes a
    span registrable in a LATER turn than the one that fetched it."""
    return Path(run.qa_dir) / CACHE_DIRNAME


def _key(url: str) -> str:
    """One URL, one identity. The key is the sha1 of the NORMALISED url
    (`retrieval.normalise_url`), so a tracking parameter or a `www.` does not
    buy a second fetch of the same document — the same identity the fusion
    already uses, rather than a second opinion about what one source is."""
    return hashlib.sha1(normalise_url(url).encode("utf-8")).hexdigest()


def sha256(text: str) -> str:
    """The hash printed beside a window and recorded in the sidecar: it ties
    an excerpt to the exact bytes of text it was taken from."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def normalise(text: str) -> str:
    """What "verbatim" means: whitespace collapsed, case folded, NOTHING
    else. The same normalisation `register_evidence` makes
    (`apps/mcp/dma_mcp/register.py`), so a span that passes the engine passes
    the connector. `casefold` rather than `lower` only because it folds the
    cases `lower` leaves (ß), which is a difference in spelling the same
    characters, not a loosening of what counts as the same text."""
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def cached_text(run, url: str) -> str | None:
    """The extracted text already held for this URL, or None."""
    p = cache_dir(run) / f"{_key(url)}.txt"
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


def store_text(run, url: str, text: str, *, content_type: str = "") -> dict:
    """Put an already-extracted text in the cache under this URL.

    The seam `--via-text` uses: a servicing actor reads a page through a
    connector's own extract (Tavily), and that text belongs in the same
    cache under the same URL so the ledger verifies an excerpt from it
    exactly as it verifies a fetched one. No second fetch is bought.
    """
    d = cache_dir(run)
    d.mkdir(parents=True, exist_ok=True)
    key = _key(url)
    (d / f"{key}.txt").write_text(text, encoding="utf-8")
    meta = {"url": url, "sha256": sha256(text), "fetched_at": _utcnow(),
            "chars": len(text), "content_type": content_type}
    (d / f"{key}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_text(run, url: str, *, fetcher=None) -> dict:
    """{text, sha256, from_cache, error} for one URL.

    SUCCESSES ARE CACHED, FAILURES ARE NEVER CACHED, and the asymmetry is
    the design, carried over from the connector's own fetcher. Measured on
    the T. Rowe Price evidence store: 120 evidence rows carry a url and 109
    are distinct, so 11 fetches repeat — and the repeats are the HEAVIEST
    documents (a DEF 14A fetched four times, a Form ADV and a BrokerCheck
    PDF three times each, each one re-run through pypdf).

    A FAILURE MUST NEVER BE CACHED. MEM-0072 was a 403 from an entity's own
    domain — transient, WAF-shaped, and the producer's correct response is
    to try again or find another source. Freezing that into a cache would
    turn a momentary block into a permanent one for the life of the run, and
    the entity would look like it has no website. It goes back uncached
    every time, WITH its reason, because a 403, an NXDOMAIN and a timeout
    each call for a different next move.

    `fetcher` is any `callable(url) -> str | None` returning already-
    extracted text; its `last_error` attribute, if it has one, is the reason
    a None came back.
    """
    held = cached_text(run, url)
    if held is not None:
        return {"text": held, "sha256": sha256(held), "from_cache": True,
                "error": None}
    f = fetcher or _http_text
    try:
        text = f(url)
    except Exception as exc:                                # noqa: BLE001
        return {"text": None, "sha256": None, "from_cache": False,
                "error": describe_error(exc, url)}
    if text is None:
        return {"text": None, "sha256": None, "from_cache": False,
                "error": (getattr(f, "last_error", None)
                          or f"no text came back from {url}")}
    meta = store_text(run, url, text,
                      content_type=getattr(f, "last_content_type", "") or "")
    return {"text": text, "sha256": meta["sha256"], "from_cache": False,
            "error": None}


# ── windows: the only part of a page that leaves this process ────────────

def _occurrences(text: str, terms: set) -> list:
    """(start, end, term) for every query term in the text, in text order.

    The run's own tokeniser (`retrieval._tokens`) decides what a term is, so
    the windows rank on the same vocabulary the BM25 rerank does rather than
    on a second opinion about word boundaries.
    """
    return [(m.start(), m.end(), m.group(0))
            for m in _TOKEN.finditer(text.lower()) if m.group(0) in terms]


def _snap(text: str, start: int, end: int) -> tuple:
    """Move the edges off the middle of a word, so a window reads as prose.

    A window that starts "...ital banking" invites the reader to quote it,
    and a half-word at the edge of an excerpt is the difference between a
    span that verifies and one that does not.
    """
    s, e = max(0, start), min(len(text), end)
    if s >= e:
        return s, e
    while s > 0 and not text[s - 1].isspace() and not text[s].isspace():
        s += 1
        if s >= e:
            return max(0, start), min(len(text), end)
    while e < len(text) and not text[e].isspace() and not text[e - 1].isspace():
        e -= 1
        if e <= s:
            return max(0, start), min(len(text), end)
    while s < e and text[s].isspace():
        s += 1
    while e > s and text[e - 1].isspace():
        e -= 1
    return (s, e) if e > s else (max(0, start), min(len(text), end))


def windows(text: str, query: str, *, window: int = DEFAULT_WINDOW,
            max_windows: int = DEFAULT_MAX_WINDOWS) -> list:
    """The `max_windows` spans of `text` densest in DISTINCT query terms.

    [{start, end, text, hits}], best first, non-overlapping, and
    `text[start:end] == text` for every one of them, so a window can be
    quoted and then verified against the same document.

    PURE. No network, no disk, no model (invariant 1) — term arithmetic
    over the run's tokeniser, so the same page and the same query give the
    same three windows on every machine, every run. Ties go to the earliest
    position, because "whichever the dict happened to yield" is not an
    answer a challenger can check.

    DISTINCT terms, not occurrences: a paragraph saying "adoption" nine
    times answers less of "Alkami digital banking adoption" than one saying
    all four once. Counting occurrences would rank the repetition first,
    which is how a navigation sidebar wins over the sentence.

    A query the page does not answer gets NO window. Silence is the honest
    answer; a window around character zero would read as a hit and be quoted
    as one.
    """
    text = str(text or "")
    terms = set(_tokens(query))
    window = max(1, int(window))
    if not text or not terms or max_windows < 1:
        return []
    occ = _occurrences(text, terms)
    if not occ:
        return []
    starts = [o[0] for o in occ]
    half = max(1, window // 2)

    def score(s: int, e: int) -> int:
        i = bisect_left(starts, s)
        seen = set()
        while i < len(occ) and occ[i][0] < e:
            if occ[i][1] <= e:
                seen.add(occ[i][2])
            i += 1
        return len(seen)

    chosen: list = []          # (hits, start, end), in the order picked
    for _ in range(int(max_windows)):
        best = None
        for o_start, o_end, _term in occ:
            # Centre the window on this occurrence, then pull it back inside
            # the text so a hit near either end still gets a full window.
            centre = (o_start + o_end) // 2
            s = max(0, centre - half)
            e = min(len(text), s + window)
            s = max(0, e - window)
            s, e = _snap(text, s, e)
            if any(s < ce and cs < e for _h, cs, ce in chosen):
                continue
            hits = score(s, e)
            # Strictly greater, so the EARLIEST of equally dense candidates
            # wins: a tie broken by iteration order is not an answer a
            # challenger can check.
            if hits and (best is None or hits > best[0]):
                best = (hits, s, e)
        if best is None:
            break
        chosen.append(best)
        _h, s, e = best
        occ = [o for o in occ if o[1] <= s or o[0] >= e]
        starts = [o[0] for o in occ]
        if not occ:
            break
    return [{"start": s, "end": e, "text": text[s:e], "hits": h}
            for h, s, e in chosen]
