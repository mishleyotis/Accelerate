"""Pure-logic tests for `app.services.run_resolver`.

The DB-touching path is covered by the e2e seed_ci suite; here we pin
the request-id validation (the one piece that doesn't need a live DB)
because that's where typo'd / cross-entity / malformed request_ids
get rejected with actionable messages.

Closes the "run selector decorative" QA finding (2026-06-05): all
six entity-scoped endpoints now route through `resolve_entity_run`,
so this regex contract is the gate that decides which inputs the
operator can paste into ?run= without getting a 500.
"""
from __future__ import annotations

import pytest

from app.services.run_resolver import _looks_like_request_id


class TestRequestIdShape:
    """The regex must accept both ID dialects we ingest (bot-originated
    REQ-{8 hex} + project-originated DMA-ASM-...) AND reject everything
    else so a typo'd ?run= surfaces a 422 instead of a 404 on a real
    UUID guess."""

    @pytest.mark.parametrize("value", [
        "REQ-ABCDEF01",
        "REQ-00000000",
        "REQ-FFFFFFFF",
        "REQ-12345678",
    ])
    def test_bot_originated_request_ids_accepted(self, value: str) -> None:
        assert _looks_like_request_id(value)

    @pytest.mark.parametrize("value", [
        "DMA-ASM-ALMABANK-20260101-0001",
        "DMA-ASM-WSFS-20260518-0042",
        "DMA-ASSESS-AMAL-20260428-0001",  # legacy variant (Amalgamated fixture)
        "DMA-ASM-REGIONS-20260518-0001",
        # RES (research) variant -- the sibling of ASM. Caught against
        # the live seeded DB on 2026-06-05: AmeriCU's run is
        # `DMA-RES-AMERICU-20260427-0001` and my initial regex
        # rejected the prefix, surfacing as 422 on /heatmap?run=.
        "DMA-RES-AMERICU-20260427-0001",
        "DMA-RES-ALMABANK-20260101-0001",
    ])
    def test_project_originated_request_ids_accepted(self, value: str) -> None:
        assert _looks_like_request_id(value)

    @pytest.mark.parametrize("value", [
        "",
        "REQ-XXXXXXXX",          # 'X' isn't hex
        "REQ-abcdef01",          # lowercase rejected -- canonical is upper
        "REQ-12345",             # too short
        "REQ-1234567890",        # too long
        "req-12345678",          # prefix lowercase
        "DMA-ASM-AlmaBank-20260101-0001",  # mixed-case rejected
        "DMA-ASM--20260101-0001",         # missing entity slug
        "DMA-ASM-ALMA-2026-0001",         # bad date width
        "00000000-0000-0000-0000-000000000000",  # raw UUID
        "some-random-string",
        "REQ-12345678 ",         # trailing whitespace
        " REQ-12345678",         # leading whitespace
        "REQ_12345678",          # underscore instead of dash
    ])
    def test_rejects_malformed_or_typo_inputs(self, value: str) -> None:
        assert not _looks_like_request_id(value)


def test_regex_patterns_are_anchored() -> None:
    """Defensive: the regex must use `^...$` so a junk prefix/suffix
    can't sneak in. Pre-anchor leakage would allow e.g.
    `REQ-12345678; DROP TABLE` to be classified as a valid request_id."""
    assert not _looks_like_request_id("REQ-12345678; DROP TABLE runs;--")
    assert not _looks_like_request_id("xxREQ-12345678")
    assert not _looks_like_request_id("REQ-12345678xx")
