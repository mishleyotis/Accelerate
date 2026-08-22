"""Fetching a source so an excerpt can be verified against it.

Lifted out of `server.py` on 2026-08-15 so it can be tested without the MCP
SDK. It was inside the transport module, which imports the SDK at module
scope, so nothing in the test suite could reach it — and the defect it
carried (a PDF decoded as UTF-8) survived in production because of exactly
that. Logic a test cannot import is logic nothing checks.
"""
from __future__ import annotations

import re


def _pdf_text(raw: bytes) -> str | None:
    """The text of a PDF, or None if it has none to give.

    MEM-0070, measured 2026-08-15 on the second client. Its own WAF answers
    403 to every HTML path while `/docs/*.pdf` returns 200, so the firm's
    substantive disclosures — client agreement, statement guides, every
    career posting — are reachable ONLY as PDFs. A producer registering from
    them scored 0 of 3; the same producer scored 13 of 13 on HTML. The span
    was verifiably present in the fetched bytes and `register_evidence`
    still answered `excerpt_not_verbatim`, because this fetcher decoded a
    binary container as UTF-8 and compared prose against mojibake.

    That refusal is the worst shape a fail-closed rule can take: it is
    indistinguishable from the producer having made the excerpt up, and the
    honest producer's only remaining moves are to drop a true finding or to
    fabricate a citation it can pass. Regulatory filings, annual reports and
    client agreements are overwhelmingly PDFs — refusing the format refuses
    the tier-1 and tier-2 sources this product is built on.

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
    except Exception:
        return None
    try:
        pages = PdfReader(io.BytesIO(raw)).pages
        text = "\n".join((p.extract_text() or "") for p in pages)
    except Exception:
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


def _describe(exc: BaseException, url: str) -> str:
    """The failure, in words a producer can act on.

    Each branch names a DIFFERENT next move, which is the whole reason the
    distinction is worth carrying: a 403 means find another source for the
    same fact, NXDOMAIN means the URL is wrong, and a timeout means try again.
    "unreachable" means all three and therefore none of them.
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
#: 403 to browser-spoofed traffic — so the header that gets us past every
#: entity WAF is precisely the one EDGAR refuses.
#:
#: It names the tool and a public contact URL. No personal address is sent:
#: EDGAR's policy asks for a way to be contacted, and a published company URL
#: is one, so there is no reason to put a person's mailbox in a header.
_DECLARED_UA = "Zennify DMA-Insights/1.0 (+https://www.zennify.com)"

#: Suffix-matched, so `data.sec.gov` and `efts.sec.gov` are covered without
#: enumerating subdomains, and a lookalike like `notsec.gov` is not.
_DECLARE_HOSTS = ("sec.gov",)


def _ua_for(url: str) -> str:
    """Which User-Agent this host wants.

    Measured 2026-08-22 against every T. Rowe Price 10-K: 403 with the
    browser UA, 200 with the declared one. This is not a bot-filter
    workaround — it is the opposite. EDGAR asks automated clients to say what
    they are, and until this existed the connector could not cite a single US
    public filer's own annual report, which is the primary source for the
    financial trajectory on every public-company assessment we produce.
    """
    m = re.match(r"^[a-z]+://([^/:?#]+)", url or "", flags=re.I)
    host = (m.group(1) if m else "").lower().rstrip(".")
    for suffix in _DECLARE_HOSTS:
        if host == suffix or host.endswith("." + suffix):
            return _DECLARED_UA
    return _BROWSER_UA


def _html_text(markup: str) -> str:
    """The prose of an HTML document, so an excerpt is compared against prose.

    The same defect `_pdf_text` fixed, one container along. A modern filing is
    inline-XBRL: every tagged figure is wrapped, so

        At December 31, 2025, we had <ix:nonFraction ...>$1,775.6</ix:nonFraction> billion

    contains the sentence a reader sees and does NOT contain it as a
    substring. Measured 2026-08-22: 0 of 5 T. Rowe Price 10-K excerpts matched
    the raw bytes; 5 of 5 match the extracted text. `register_evidence`
    answered `excerpt_not_verbatim` — a refusal indistinguishable from the
    producer having invented the citation, whose only remaining moves are to
    drop a true finding or to fabricate one it can pass.

    INLINE TAGS CLOSE UP, BLOCK TAGS BECOME A SPACE. `<b>Fin</b>ancial` is one
    word and must not become two; `<td>a</td><td>b</td>` is two and must not
    become one. Getting that backwards silently corrupts every comparison.

    Extraction only — no fuzzy matching, no repair. The verbatim comparison
    downstream still normalises nothing but whitespace and case.
    """
    import html as _html
    s = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", markup)
    s = re.sub(r"(?is)<!--.*?-->", " ", s)
    s = re.sub(r"(?i)</?(p|div|br|hr|tr|td|th|li|ul|ol|dl|dd|dt|h[1-6]|table|"
               r"thead|tbody|tfoot|section|article|header|footer|nav|aside|"
               r"blockquote|pre|figure|figcaption|option)\b[^>]*>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return _html.unescape(s)


#: How long an extracted document stays usable. A page's worth of
#: registrations happens in minutes; beyond that the document should be read
#: again, because "is this span in the current document" is the question.
CACHE_TTL_SECONDS = 900
#: Total characters held. Roughly 40MB of text — a handful of filings — on a
#: 2Gi container. Oldest out first.
CACHE_MAX_CHARS = 40_000_000

_cache: dict = {}          # url -> (stored_at_monotonic, text)


def _cache_get(url: str, now: float):
    hit = _cache.get(url)
    if hit is None:
        return None
    stored_at, text = hit
    if now - stored_at > CACHE_TTL_SECONDS:
        _cache.pop(url, None)
        return None
    return text


def _cache_put(url: str, text: str, now: float) -> None:
    _cache[url] = (now, text)
    total = sum(len(t) for _, t in _cache.values())
    while total > CACHE_MAX_CHARS and len(_cache) > 1:
        oldest = min(_cache, key=lambda k: _cache[k][0])
        total -= len(_cache.pop(oldest)[1])


def _fetch(url: str):
    """Excerpt-verification fetcher: GET with the User-Agent this host wants,
    TEXT out, None on failure.

    Neither PDFs nor HTML are handed back as their container: `_pdf_text`
    extracts the one, `_html_text` the other, so what the caller compares an
    excerpt against is always prose.

    SUCCESSES ARE CACHED, FAILURES ARE NOT, and the asymmetry is the whole
    design. Measured on the T. Rowe Price evidence store: 120 rows carry a
    url and 109 are distinct, so 11 fetches repeat — a 9% hit rate that
    understates the saving badly, because the repeats are the HEAVIEST
    documents. A DEF 14A proxy statement is fetched four times and a Form ADV
    and a BrokerCheck PDF three times each, and every PDF is run through
    `pypdf` extraction again on each one.

    A FAILURE MUST NEVER BE CACHED. MEM-0072 was a 403 from an entity's own
    domain — transient, WAF-shaped, and the producer's correct response is to
    try again or find another source. Freezing that into a cache would turn a
    momentary block into a permanent one for the rest of the process's life,
    and the entity would look like it has no website. `None` goes back
    uncached every time.
    """
    import time
    import urllib.request

    now = time.monotonic()
    cached = _cache_get(url, now)
    if cached is not None:
        return cached
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _ua_for(url),
            # `*/*` last, but application/pdf named explicitly: a server that
            # content-negotiates will not offer a PDF to a client whose Accept
            # header only ever asked for HTML.
            "Accept": ("text/html,application/xhtml+xml,application/pdf,"
                       "application/xml;q=0.9,*/*;q=0.8"),
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(20_000_000)
            ctype = (r.headers.get("Content-Type") or "").lower()
    except Exception as exc:                      # noqa: BLE001
        # WHY IT FAILED, not merely THAT it failed.
        #
        # This was `except Exception: return None`, so `register_evidence`
        # answered `url_unreachable` for a DNS failure, a TLS error, a 403
        # from a WAF, a 404, a redirect loop and a timeout alike. MEM-0072
        # has been an open BLOCKER on exactly that: the connector cannot
        # reach an entity's own site or its regulators, and no one could tell
        # whether the cause was egress, the User-Agent, or the site being
        # gone — so nobody could fix it. Measured again 2026-08-16 on a second
        # client, whose own domain and three regulator hosts all returned the
        # same undifferentiated word.
        #
        # A producer cannot act on "unreachable". It can act on "403 from
        # Cloudflare", which means find another source, and on "DNS NXDOMAIN",
        # which means the URL is wrong. Recorded on the function so the caller
        # can surface it without changing its own signature.
        _fetch.last_error = _describe(exc, url)
        return None
    # MAGIC BYTES DECIDE, not the URL and not the header alone. A filing
    # served as application/octet-stream is still a PDF, and a `.pdf` path
    # that 200s with an HTML error page is still HTML — trusting either one
    # alone gets the common cases backwards.
    if raw[:5] == b"%PDF-" or "application/pdf" in ctype:
        text = _pdf_text(raw)
    else:
        text = _html_text(raw.decode("utf-8", "replace"))
    # A scanned PDF extracts to None — an unreachable document, not an empty
    # one — and takes the same uncached path as any other failure.
    if text is not None:
        _cache_put(url, text, now)
    return text


#: Last failure reason, set by `_fetch` and read by callers that report it.
#: Initialised so a read before any fetch is None rather than AttributeError.
_fetch.last_error = None
