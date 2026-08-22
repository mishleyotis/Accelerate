"""Why a fetch failed, not merely that it did.

`_fetch` caught every exception and returned None, so `register_evidence`
answered `url_unreachable` for a DNS failure, a TLS error, a 403 from a bot
filter, a 404, a redirect loop and a timeout alike. MEM-0072 has been an open
BLOCKER across two clients on exactly that: nobody could tell whether the
connector could not reach an entity's own site because of egress, the
User-Agent, or the site being gone — so nobody could fix it.

The distinction is not cosmetic. "This firm's site refuses robots" is evidence
about NOTHING; "this firm has no site" is evidence about the firm. The one
word collapsed them, which is how a bot filter becomes a recorded absence.
"""
import socket as _socket
import ssl as _ssl
import sys
import urllib.error as _uerr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.fetching import _describe, _fetch      # noqa: E402


def test_A_BOT_FILTER_IS_NOT_AN_ABSENCE():
    msg = _describe(
        _uerr.HTTPError("https://x/y", 403, "Forbidden", {}, None),
        "https://clientsite.com/about")
    assert "403" in msg and "clientsite.com" in msg
    assert "another source" in msg, (
        "a 403 must tell the producer to cite the fact elsewhere; recording an "
        "absence from a bot filter is the failure this exists to stop")


def test_a_missing_page_says_the_url_is_wrong_not_the_capability_is_absent():
    msg = _describe(_uerr.HTTPError("https://x/y", 404, "NF", {}, None),
                    "https://clientsite.com/gone")
    assert "404" in msg
    assert "about the URL, not the capability" in msg


def test_dns_failure_is_distinguishable_from_a_refusal():
    msg = _describe(_uerr.URLError(_socket.gaierror(-2, "no host")),
                    "https://nope.invalid/x")
    assert "DNS" in msg and "nope.invalid" in msg
    assert "403" not in msg


def test_tls_and_timeout_are_their_own_answers():
    assert "TLS" in _describe(_uerr.URLError(_ssl.SSLError("bad")), "https://h/x")
    assert "timed out" in _describe(
        _uerr.URLError(_socket.timeout()), "https://h/x")


def test_every_branch_names_the_host():
    """A reason with no host is not actionable when a payload cites forty."""
    for exc in (_uerr.HTTPError("https://x/y", 403, "F", {}, None),
                _uerr.HTTPError("https://x/y", 500, "E", {}, None),
                _uerr.URLError(_socket.gaierror(-2, "x")),
                _uerr.URLError(_ssl.SSLError("bad")),
                _uerr.URLError(_socket.timeout()),
                ValueError("odd")):
        assert "myhost.example" in _describe(exc, "https://myhost.example/a")


def test_THE_REASON_REACHES_THE_CALLER():
    """A described failure nobody can read is the same as no description.
    `_fetch` records it where `register_evidence` looks."""
    assert _fetch("https://this-host-does-not-exist-xyz.invalid/a") is None
    assert _fetch.last_error and "this-host-does-not-exist-xyz.invalid" in _fetch.last_error


def test_the_attribute_exists_before_any_fetch_runs():
    """Read before first use must be None, not AttributeError — the caller
    uses getattr with a default, but a module that cannot be introspected
    without calling it is a trap for the next reader."""
    import importlib

    import dma_mcp.fetching as F
    importlib.reload(F)
    assert F._fetch.last_error is None
