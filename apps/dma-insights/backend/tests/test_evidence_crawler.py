"""evidence_crawler pure-logic tests — the SSRF gate, passage extraction, the
cross-encoder-grounded excerpt pick, and the host circuit breaker. All offline
and tier-robust (the grounded pick degrades to the bi-encoder cosine when the
cross-encoder is cold, so these hold hot and cold).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workers.evidence_crawler import service as S  # noqa: E402


# ── SSRF gate ────────────────────────────────────────────────────────────
def test_scheme_gate_rejects_nonhttp_and_internal() -> None:
    assert S.url_scheme_host_ok("ftp://example.com/x")[0] is False
    assert S.url_scheme_host_ok("file:///etc/passwd")[0] is False
    assert S.url_scheme_host_ok("http://localhost/x")[0] is False
    assert S.url_scheme_host_ok("http://metadata.google.internal/x")[0] is False
    # literal private / link-local IPs
    assert S.url_scheme_host_ok("http://169.254.169.254/latest")[0] is False
    assert S.url_scheme_host_ok("http://10.0.0.5/x")[0] is False
    assert S.url_scheme_host_ok("http://127.0.0.1/x")[0] is False


def test_scheme_gate_allows_public() -> None:
    assert S.url_scheme_host_ok("https://www.sec.gov/filing")[0] is True
    assert S.url_scheme_host_ok("https://www.globenewswire.com/news")[0] is True
    # public literal IP is allowed at the scheme gate (DNS check is separate)
    assert S.url_scheme_host_ok("https://8.8.8.8/")[0] is True


def test_ip_is_public_classifies_ranges() -> None:
    assert S.ip_is_public("8.8.8.8") is True
    assert S.ip_is_public("169.254.169.254") is False   # link-local (metadata)
    assert S.ip_is_public("10.1.2.3") is False
    assert S.ip_is_public("192.168.0.1") is False
    assert S.ip_is_public("127.0.0.1") is False
    assert S.ip_is_public("not-an-ip") is False


def test_acceptable_content_type() -> None:
    assert S.acceptable_content_type("text/html; charset=utf-8") is True
    assert S.acceptable_content_type("application/xhtml+xml") is True
    assert S.acceptable_content_type("application/pdf") is False
    assert S.acceptable_content_type("image/png") is False
    assert S.acceptable_content_type(None) is False


# ── passage extraction ────────────────────────────────────────────────────
def test_extract_passages_strips_boilerplate_and_splits() -> None:
    html = (
        "<html><head><style>.x{}</style></head><body>"
        "<script>var a=1;</script>"
        "<nav>Home About Contact</nav>"
        "<p>Guaranteed Rate named Jason Stenger as Chief Production Officer to "
        "lead national production strategy and scale originator support.</p>"
        "<p>The appointment strengthens executive sponsorship of the digital "
        "lending roadmap across the retail book.</p>"
        "<footer>Copyright 2025</footer></body></html>"
    )
    passages = S.extract_passages(html)
    joined = " ".join(passages)
    assert "var a=1" not in joined and "Copyright 2025" not in joined
    assert any("Chief Production Officer" in p for p in passages)
    assert all(S._MIN_PASSAGE <= len(p) <= S._MAX_PASSAGE for p in passages)


def test_extract_passages_never_raises_on_garbage() -> None:
    assert S.extract_passages("") == []
    assert isinstance(S.extract_passages("<<< not really html >>>"), list)


# ── cross-encoder-grounded excerpt pick ────────────────────────────────────
def test_best_excerpt_prefers_supporting_passage() -> None:
    capability = "Executive Sponsorship. Senior leadership owns the digital agenda."
    passages = [
        "The quarterly bake sale raised funds for the local animal shelter.",
        "The CEO personally sponsors the digital transformation program and "
        "chairs its steering committee, owning the executive agenda.",
        "Parking rates in the downtown garage increased in March.",
    ]
    hit = S.best_excerpt(capability, passages, floor=0.0)
    assert hit is not None
    top, score = hit
    assert "sponsors the digital transformation" in top
    assert 0.0 <= score <= 1.0


def test_best_excerpt_returns_none_below_floor_and_on_empty() -> None:
    assert S.best_excerpt("anything", [], floor=0.30) is None
    assert S.best_excerpt("", ["some passage text here that is long enough"],
                          floor=0.30) is None
    # an impossibly high floor → nothing qualifies → honest None
    hit = S.best_excerpt(
        "Executive Sponsorship",
        ["Parking rates in the downtown garage increased in March this year."],
        floor=0.99)
    assert hit is None


def test_build_capability_query_prefers_subcaps_then_source() -> None:
    q = S.build_capability_query(
        "GlobeNewswire - CPO appointment",
        ["Executive Sponsorship. Leadership owns the agenda."],
        "EVIDENCE")
    assert q.startswith("Executive Sponsorship")
    assert "GlobeNewswire" in q
    # empty-safe: falls back to claim_type
    assert S.build_capability_query(None, [], "FACT") == "FACT"


# ── host circuit breaker ───────────────────────────────────────────────────
def test_host_breaker_trips_after_limit() -> None:
    b = S.HostBreaker(fail_limit=3)
    h = "walled.example.com"
    assert b.should_skip(h) is False
    b.record_fail(h)
    b.record_fail(h)
    assert b.should_skip(h) is False        # 2 fails, still under limit
    b.record_fail(h)
    assert b.should_skip(h) is True         # 3rd fail trips it
    assert h in b.tripped_hosts


def test_host_breaker_reset_on_success() -> None:
    b = S.HostBreaker(fail_limit=2)
    h = "flaky.example.com"
    b.record_fail(h)
    b.record_ok(h)                          # success resets the counter
    b.record_fail(h)
    assert b.should_skip(h) is False        # only 1 fail since reset


def test_host_of() -> None:
    assert S.host_of("https://www.SEC.gov/path") == "www.sec.gov"
    assert S.host_of("not a url") == ""
