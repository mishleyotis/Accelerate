"""Pure, IO-free core of the evidence-excerpt crawler.

Everything here is deterministic and side-effect-free so it is unit-testable
without a network or DB: the SSRF gate, HTML→passage extraction, the
cross-encoder-grounded excerpt selection, and the per-host circuit breaker. The
network/DB IO lives in ``live.py``; the CLI + job tracking in ``main.py``.

Grounding contract (the reason this exists rather than a Gemini "write me an
excerpt" call): the excerpt is ALWAYS a verbatim passage taken from the fetched
page and only kept when the cross-encoder confirms it supports the cited
capability at or above ``SUPPORT_FLOOR``. Nothing is generated. If the fetch
fails or no passage clears the floor, the row stays honestly empty — a made-up
quote is worse than a missing one.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# The cross-encoder fused-support floor to ATTACH a crawled excerpt — the same
# bar link_evidence_subcaps / derive_insights use, so a crawled excerpt is held
# to the identical grounding standard as every other citation.
SUPPORT_FLOOR = 0.30
_MIN_PASSAGE = 60
_MAX_PASSAGE = 320
_MAX_PASSAGES = 400
# host circuit breaker: after this many consecutive failures a host is skipped
# for the rest of the run (LinkedIn/Glassdoor login walls, a down host, etc.).
_HOST_FAIL_LIMIT = 3

# Content types worth extracting text from.
_OK_CONTENT_TYPES = ("text/html", "application/xhtml", "text/plain")

# Hostnames that must never be fetched regardless of DNS (cloud metadata, etc.).
_BLOCKED_HOSTS = frozenset({
    "metadata.google.internal", "metadata", "localhost", "localhost.localdomain",
})


# ── SSRF gate ──────────────────────────────────────────────────────────────
def url_scheme_host_ok(url: str) -> tuple[bool, str]:
    """Cheap, DNS-free first gate: scheme + obviously-internal host/literal-IP.
    The authoritative resolved-IP check is ``resolve_public_ips`` (needs DNS, so
    it lives in the IO path). Returns (ok, reason)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False, "unparseable url"
    if parts.scheme not in ("http", "https"):
        return False, f"scheme {parts.scheme!r} not allowed"
    host = (parts.hostname or "").strip().lower()
    if not host:
        return False, "no host"
    if host in _BLOCKED_HOSTS:
        return False, f"blocked host {host!r}"
    # literal IP → must be public now. Hostnames are validated after DNS.
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True, "hostname (validate IPs after DNS)"
    return (True, "public literal-ip") if ip_is_public(host) else (False, "non-public literal-ip")


def ip_is_public(ip_str: str) -> bool:
    """Is a resolved IP safe to fetch (public, non-internal)?"""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return ip.is_global and not (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_multicast or ip.is_reserved or ip.is_unspecified
    )


def resolve_public_ips(host: str) -> tuple[bool, str]:
    """DNS-resolve ``host`` and require EVERY resolved address to be public —
    blocks DNS-rebinding to an internal/metadata address. IO (getaddrinfo);
    kept here so the gate is one call. Returns (ok, reason)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as e:
        return False, f"dns: {e!s}"[:80]
    ips = {i[4][0] for i in infos}
    if not ips:
        return False, "dns: no addresses"
    bad = [ip for ip in ips if not ip_is_public(ip)]
    if bad:
        return False, f"resolves to non-public {bad[:2]}"
    return True, "public"


def acceptable_content_type(content_type: str | None) -> bool:
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    return any(ct.startswith(p) for p in _OK_CONTENT_TYPES)


# ── HTML → candidate passages ───────────────────────────────────────────────
_WS_RE = re.compile(r"\s+")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def extract_passages(
    html: str, *, min_len: int = _MIN_PASSAGE, max_len: int = _MAX_PASSAGE,
    limit: int = _MAX_PASSAGES,
) -> list[str]:
    """Strip boilerplate, split the visible text into sentence-ish passages,
    dedup, and cap. Uses bs4+lxml when available, falling back to a regex tag
    strip so it never hard-depends on the parser."""
    text = _visible_text(html)
    text = _WS_RE.sub(" ", text).strip()
    out: list[str] = []
    seen: set[str] = set()
    for p in _SENT_SPLIT_RE.split(text):
        p = p.strip()
        if min_len <= len(p) <= max_len and p not in seen:
            seen.add(p)
            out.append(p)
            if len(out) >= limit:
                break
    return out


def _visible_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for t in soup(["script", "style", "nav", "footer", "header",
                       "form", "noscript", "svg"]):
            t.decompose()
        return soup.get_text(" ")
    except Exception:
        # parser-free fallback: drop tags crudely so the crawler never raises.
        no_tags = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        return re.sub(r"(?s)<[^>]+>", " ", no_tags)


# ── cross-encoder-grounded excerpt selection ────────────────────────────────
def build_capability_query(
    source_name: str | None, subcap_texts: list[str], claim_type: str | None,
) -> str:
    """The text the cross-encoder ranks passages against: the linked capability
    label(s) lead (they are the semantic target), with the source_name as a
    lighter hint. Empty-safe."""
    parts = [t for t in subcap_texts if t]
    if source_name:
        parts.append(source_name)
    q = ". ".join(parts).strip()
    return q or (claim_type or "")


def best_excerpt(
    capability: str, passages: list[str], *, floor: float = SUPPORT_FLOOR,
) -> tuple[str, float] | None:
    """Pick the passage that best SUPPORTS ``capability`` via the two-tier
    retrieve-then-rerank signal (bi-encoder recall → cross-encoder support),
    the identical scorer the derive path uses. Returns (passage, support) when
    the top passage clears ``floor``, else None (→ leave the row empty). Never
    raises — a cold NLP tier degrades to the bi-encoder cosine."""
    if not capability or not passages:
        return None
    from app.services.nlp import rerank
    from app.services.nlp.semantic import SemanticIndex
    idx = SemanticIndex()
    scored = [
        (p, rerank.support_score(capability, p, idx.relevance(capability, p)))
        for p in passages
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    top, score = scored[0]
    return (top, score) if score >= floor else None


# ── per-host circuit breaker + politeness state ──────────────────────────────
@dataclass
class HostBreaker:
    """Tracks consecutive per-host failures so a dead / bot-hostile host is
    abandoned instead of consuming the run's budget on repeated timeouts."""
    fail_limit: int = _HOST_FAIL_LIMIT
    _fails: dict[str, int] = field(default_factory=dict)
    _tripped: set[str] = field(default_factory=set)

    def should_skip(self, host: str) -> bool:
        return host in self._tripped

    def record_ok(self, host: str) -> None:
        self._fails[host] = 0

    def record_fail(self, host: str) -> None:
        n = self._fails.get(host, 0) + 1
        self._fails[host] = n
        if n >= self.fail_limit:
            self._tripped.add(host)

    @property
    def tripped_hosts(self) -> list[str]:
        return sorted(self._tripped)


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
