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


def _fetch(url: str):
    """Excerpt-verification fetcher: GET with a browser-shaped UA (bare
    python-urllib is WAF-blocked by most entity sites — bcu.org rejected
    the first prod registration), text out, None on failure.

    PDFs are extracted rather than decoded; see `_pdf_text`."""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
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
        return _pdf_text(raw)
    return raw.decode("utf-8", "replace")


#: Last failure reason, set by `_fetch` and read by callers that report it.
#: Initialised so a read before any fetch is None rather than AttributeError.
_fetch.last_error = None
