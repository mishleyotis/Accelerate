"""Tests for evidence dedup primitives.

State-transition coverage matrix (per scope §3 — all 4+1 branches):

  - kept                   → test_first_sighting_is_kept
  - dedup_same_entity      → test_same_entity_existing_dedups
  - cross_entity_kept      → test_different_entity_kept_independently
  - duplicate_within_run   → test_seen_in_run_marks_duplicate
  - tier_upgrade           → test_lower_tier_triggers_upgrade
"""
from __future__ import annotations

from app.services.evidence_dedup import (
    ExistingEvidence,
    IncomingEvidence,
    compute_content_hash,
    decide,
    normalize_excerpt,
)


class TestNormalize:
    def test_collapses_whitespace_and_lowers(self) -> None:
        # Per the SQL contract (migration 018), whitespace runs are
        # collapsed to single spaces but outer whitespace is PRESERVED
        # (no trim). The Python helper matches this verbatim — diverging
        # from SQL silently broke dedup parity, see the regression note
        # in `evidence_dedup.normalize_excerpt`.
        assert normalize_excerpt("  Hello\tWorld\n") == " hello world "

    def test_clips_to_500_chars(self) -> None:
        s = "x" * 600
        assert len(normalize_excerpt(s)) == 500

    def test_empty_safe(self) -> None:
        assert normalize_excerpt(None) == ""
        assert normalize_excerpt("") == ""

    def test_python_matches_sql_contract_for_typical_inputs(self) -> None:
        """Pins the Python/SQL parity contract for migration 018's
        ``compute_evidence_freshness_band`` / content_hash backfill.

        Any future refactor that re-introduces a ``.strip()`` here will
        trip this test BEFORE shipping a bad hash to production.
        """
        # Outer whitespace preserved
        assert normalize_excerpt("  a b  ") == " a b "
        # Tabs / newlines collapse to single space
        assert normalize_excerpt("a\tb\nc") == "a b c"
        # Lowering happens AFTER the regex collapse — same result for
        # ASCII; the order matters for unicode mixed-case whitespace.
        assert normalize_excerpt("AbC") == "abc"


class TestContentHash:
    def test_same_inputs_same_hash(self) -> None:
        h1 = compute_content_hash(
            source_url="https://x", claim_type="FACT", excerpt="some quote",
        )
        h2 = compute_content_hash(
            source_url="https://x", claim_type="FACT", excerpt="some quote",
        )
        assert h1 == h2
        assert len(h1) == 64

    def test_internal_whitespace_collapse_dedups(self) -> None:
        """Internal-whitespace differences DO dedup (multi-space ≡ single)."""
        h1 = compute_content_hash(
            source_url="https://x", claim_type="FACT", excerpt="some quote",
        )
        h2 = compute_content_hash(
            source_url="https://x", claim_type="FACT", excerpt="some\tquote",
        )
        h3 = compute_content_hash(
            source_url="https://x", claim_type="FACT", excerpt="some   quote",
        )
        assert h1 == h2 == h3

    def test_outer_whitespace_does_NOT_dedup_matches_sql_contract(self) -> None:
        """Adversarial test for the Python/SQL parity regression caught
        2026-05-26. The SQL backfill does NOT trim outer whitespace —
        Python must therefore also leave outer whitespace intact, even
        though it means a leading-space variant of the same quote is
        treated as distinct.

        This is documented in `normalize_excerpt`'s docstring as a
        known dedup-strictness footgun. A future migration (022) could
        add `trim()` to both sides; until then both sides MUST agree.
        """
        h_no_ws = compute_content_hash(
            source_url="https://x", claim_type="FACT", excerpt="some quote",
        )
        h_lead_ws = compute_content_hash(
            source_url="https://x", claim_type="FACT", excerpt=" some quote",
        )
        # Same content, different hash — by SQL contract.
        assert h_no_ws != h_lead_ws

    def test_url_change_changes_hash(self) -> None:
        h1 = compute_content_hash(
            source_url="https://x", claim_type="FACT", excerpt="q",
        )
        h2 = compute_content_hash(
            source_url="https://y", claim_type="FACT", excerpt="q",
        )
        assert h1 != h2


def _incoming(
    *, e_id="E-001", url="https://x", claim="FACT",
    excerpt="q", tier=5, entity="ent-A", run="run-1",
) -> IncomingEvidence:
    return IncomingEvidence(
        e_id=e_id, source_url=url, claim_type=claim, excerpt=excerpt,
        tier=tier, entity_id=entity, run_id=run,
    )


class TestDecide:
    def test_first_sighting_is_kept(self) -> None:
        inc = _incoming()
        dec = decide(
            inc, existing_same_entity=None,
            existing_other_entity=None, seen_in_this_run=False,
        )
        assert dec.action == "kept"
        assert dec.kept_evidence_id is None
        assert dec.upgraded_tier_to is None

    def test_same_entity_existing_dedups(self) -> None:
        inc = _incoming(tier=5)
        existing = ExistingEvidence(
            evidence_id="evi-1", entity_id="ent-A", tier=5,
            content_hash=inc.content_hash,
        )
        dec = decide(
            inc, existing_same_entity=existing,
            existing_other_entity=None, seen_in_this_run=False,
        )
        assert dec.action == "dedup_same_entity"
        assert dec.kept_evidence_id == "evi-1"

    def test_different_entity_kept_independently(self) -> None:
        inc = _incoming(entity="ent-A")
        other = ExistingEvidence(
            evidence_id="evi-9", entity_id="ent-B", tier=4,
            content_hash=inc.content_hash,
        )
        dec = decide(
            inc, existing_same_entity=None,
            existing_other_entity=other, seen_in_this_run=False,
        )
        assert dec.action == "cross_entity_kept"
        # Caller inserts a NEW row scoped to ent-A — no link to evi-9.
        assert dec.kept_evidence_id is None

    def test_seen_in_run_marks_duplicate(self) -> None:
        inc = _incoming()
        dec = decide(
            inc, existing_same_entity=None,
            existing_other_entity=None, seen_in_this_run=True,
        )
        assert dec.action == "duplicate_within_run"

    def test_lower_tier_triggers_upgrade(self) -> None:
        """incoming.tier=3 (stronger) vs existing.tier=5 → tier_upgrade."""
        inc = _incoming(tier=3)
        existing = ExistingEvidence(
            evidence_id="evi-1", entity_id="ent-A", tier=5,
            content_hash=inc.content_hash,
        )
        dec = decide(
            inc, existing_same_entity=existing,
            existing_other_entity=None, seen_in_this_run=False,
        )
        assert dec.action == "tier_upgrade"
        assert dec.upgraded_tier_to == 3
        assert dec.kept_evidence_id == "evi-1"
        assert "tier=3" in dec.reason

    def test_higher_tier_just_dedups(self) -> None:
        """incoming.tier=7 (weaker) vs existing.tier=5 → plain dedup, no upgrade."""
        inc = _incoming(tier=7)
        existing = ExistingEvidence(
            evidence_id="evi-1", entity_id="ent-A", tier=5,
            content_hash=inc.content_hash,
        )
        dec = decide(
            inc, existing_same_entity=existing,
            existing_other_entity=None, seen_in_this_run=False,
        )
        assert dec.action == "dedup_same_entity"

    def test_seen_in_run_wins_over_existing(self) -> None:
        """Within-run dup detection beats every cross-row check."""
        inc = _incoming()
        existing = ExistingEvidence(
            evidence_id="evi-1", entity_id="ent-A", tier=5,
            content_hash=inc.content_hash,
        )
        dec = decide(
            inc, existing_same_entity=existing,
            existing_other_entity=None, seen_in_this_run=True,
        )
        assert dec.action == "duplicate_within_run"
