"""Tests for the dedup-aware evidence persistence in package_persist.

State-transition coverage matrix (all 5 dedup_audit action values):

  - kept                  → test_first_sighting_inserts_row_and_links_run
  - dedup_same_entity     → test_reingest_same_package_links_existing_row
  - cross_entity_kept     → test_cross_entity_same_url_keeps_independent_rows
  - tier_upgrade          → test_lower_tier_upgrades_existing_row
  - duplicate_within_run  → test_duplicate_within_run_is_skipped

These tests use an in-memory FakeSession to mock SQLAlchemy
`execute()`. The point is to prove the BRANCH ROUTING of
`_persist_evidence` — that the correct SQL gets queued for each dedup
action with the correct params — not to round-trip Postgres. The
evidence_dedup decision engine itself is exhaustively tested in
test_evidence_dedup.py.

Part 12.4 (2026-07) batching contract update: `_persist_evidence` now
does TWO batched hash lookups (same-entity / other-entity, `content_hash
= ANY(:hashes)`) + one (run_id → e_id, id) prefetch up front, queues the
per-row decisions, and flushes ≤4 executemany statements (evidence
inserts with client-generated ids, tier updates, run links, audits).
The FakeSession therefore returns LIST results for the batched lookups
and the assertion helpers flatten executemany param lists.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.services.evidence_dedup import (
    compute_content_hash,
)

# ---------------------------------------------------------------------
# FakeSession — records every executed SQL/params pair for assertions
# ---------------------------------------------------------------------


class _Row:
    """SQLAlchemy-Row-shaped lookup-by-attr."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Result:
    def __init__(self, rows: list[_Row] | None = None, scalar: Any = None):
        self._rows = rows or []
        self._scalar = scalar
        self.rowcount = len(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar

    def mappings(self):
        return self


class FakeSession:
    """Records (sql_text, params) tuples; returns configurable results.

    ``same_rows`` / ``other_rows`` seed the two batched content-hash
    lookups (same-entity / other-entity scope). Each row must carry the
    REAL ``content_hash`` for the evidence it should match — the
    batched implementation keys its maps on that column.
    """

    def __init__(self):
        self.calls: list[tuple[str, Any]] = []
        self.same_rows: list[_Row] = []
        self.other_rows: list[_Row] = []

    async def execute(self, sql, params=None):
        sql_text = str(sql)
        if isinstance(params, list):
            self.calls.append((sql_text, [dict(p) for p in params]))
        else:
            self.calls.append((sql_text, dict(params or {})))

        if (
            "FROM evidence_index" in sql_text
            and "content_hash = ANY" in sql_text
        ):
            if "entity_id = CAST" in sql_text:
                return _Result(rows=self.same_rows)
            return _Result(rows=self.other_rows)
        if "SELECT e_id, id::text AS id FROM evidence_index" in sql_text:
            # (run_id → existing e_id/id) prefetch: fresh run → empty.
            return _Result(rows=[])
        return _Result(rows=[])


# ---------------------------------------------------------------------
# Fixtures: pretend Pkg.evidence entries
# ---------------------------------------------------------------------


class _Ev:
    def __init__(self, *, e_id="E-001", source_name="Source",
                 source_url="https://x", excerpt="exc",
                 tier=5, signal_direction="FACT",
                 subcap_mappings=None, publish_date=None):
        self.e_id = e_id
        self.source_name = source_name
        self.source_url = source_url
        self.excerpt = excerpt
        self.tier = tier
        self.signal_direction = signal_direction
        self.subcap_mappings = subcap_mappings or []
        self.publish_date = publish_date


class _Pkg:
    def __init__(self, evidence: list[_Ev]):
        self.evidence = evidence


def _hash_of(ev: _Ev) -> str:
    return compute_content_hash(
        source_url=ev.source_url,
        claim_type=ev.signal_direction or "EVIDENCE",
        excerpt=ev.excerpt or "(no excerpt)",
    )


# ---------------------------------------------------------------------
# Helpers to assert call patterns (flatten executemany param lists)
# ---------------------------------------------------------------------


def _rows_matching(session: FakeSession, fragment: str) -> list[dict]:
    out: list[dict] = []
    for s, p in session.calls:
        if fragment.lower() not in s.lower():
            continue
        if isinstance(p, list):
            out.extend(p)
        else:
            out.append(p)
    return out


def _find_audit_rows(session: FakeSession) -> list[dict]:
    return _rows_matching(session, "INSERT INTO dedup_audit")


def _find_link_rows(session: FakeSession) -> list[dict]:
    return _rows_matching(session, "INSERT INTO evidence_run_links")


def _find_insert_evidence_rows(session: FakeSession) -> list[dict]:
    return _rows_matching(session, "INSERT INTO evidence_index")


def _find_tier_update_rows(session: FakeSession) -> list[dict]:
    return [
        p for (s, params) in session.calls
        if "UPDATE evidence_index" in s and "tier" in s
        for p in (params if isinstance(params, list) else [params])
    ]


# ---------------------------------------------------------------------
# Cases: each test invokes _persist_evidence and verifies branch routing
# ---------------------------------------------------------------------


from app.services.parsers.package_persist import _persist_evidence  # noqa: E402


class TestKeptBranch:
    def test_first_sighting_inserts_row_and_links_run(self) -> None:
        """`kept` — no existing row → INSERT evidence + LINK (first_seen=True)
        + audit_action='kept'."""
        session = FakeSession()
        pkg = _Pkg([_Ev(e_id="E-1", excerpt="hello world")])
        asyncio.run(_persist_evidence(
            session, run_id="run-1", entity_id="ent-A", pkg=pkg,
        ))

        inserts = _find_insert_evidence_rows(session)
        assert len(inserts) == 1
        assert inserts[0]["ch"] == compute_content_hash(
            source_url="https://x", claim_type="FACT", excerpt="hello world",
        )
        # Client-generated UUID rides the batched insert.
        assert inserts[0]["id"]

        links = _find_link_rows(session)
        assert len(links) == 1
        assert links[0]["fs"] is True
        assert links[0]["e"] == inserts[0]["id"]

        audits = _find_audit_rows(session)
        assert len(audits) == 1
        assert audits[0]["act"] == "kept"


class TestDedupSameEntity:
    def test_reingest_same_package_links_existing_row(self) -> None:
        """`dedup_same_entity` — re-ingest finds existing row in this
        entity → no INSERT evidence; LINK existing (first_seen=False)
        + audit_action='dedup_same_entity'."""
        session = FakeSession()
        existing_id = "11111111-1111-1111-1111-111111111111"
        ev = _Ev(e_id="E-1", excerpt="repeat me")
        # Same-entity lookup returns an existing row (same tier so no
        # upgrade) keyed by the REAL content hash.
        session.same_rows = [
            _Row(evidence_id=existing_id, entity_id="ent-A",
                 tier=5, content_hash=_hash_of(ev)),
        ]
        pkg = _Pkg([ev])
        asyncio.run(_persist_evidence(
            session, run_id="run-2", entity_id="ent-A", pkg=pkg,
        ))

        # ZERO inserts into evidence_index.
        assert _find_insert_evidence_rows(session) == []

        links = _find_link_rows(session)
        assert len(links) == 1
        assert links[0]["e"] == existing_id
        assert links[0]["rid"] == "run-2"
        assert links[0]["fs"] is False

        audits = _find_audit_rows(session)
        assert len(audits) == 1
        assert audits[0]["act"] == "dedup_same_entity"
        assert audits[0]["ke"] == existing_id

    def test_two_reingests_double_the_run_links(self) -> None:
        """The contract: ingest twice → evidence_index unchanged, but
        evidence_run_links has 2 rows for the same evidence_id."""
        # First ingest: kept.
        s1 = FakeSession()
        ev = _Ev(e_id="E-1", excerpt="x")
        pkg = _Pkg([ev])
        asyncio.run(_persist_evidence(
            s1, run_id="run-1", entity_id="ent-A", pkg=pkg,
        ))
        assert len(_find_insert_evidence_rows(s1)) == 1

        # Second ingest: dedup_same_entity.
        s2 = FakeSession()
        s2.same_rows = [
            _Row(evidence_id="kept-1", entity_id="ent-A",
                 tier=5, content_hash=_hash_of(ev)),
        ]
        asyncio.run(_persist_evidence(
            s2, run_id="run-2", entity_id="ent-A", pkg=pkg,
        ))
        audits1 = _find_audit_rows(s1)
        audits2 = _find_audit_rows(s2)
        assert audits1[0]["act"] == "kept"
        assert audits2[0]["act"] == "dedup_same_entity"
        # Across the two, evidence_index inserts = 1 (only the first).
        # Links across two runs = 2 (one per run).
        assert len(_find_insert_evidence_rows(s1)) \
            + len(_find_insert_evidence_rows(s2)) == 1
        assert len(_find_link_rows(s1)) + len(_find_link_rows(s2)) == 2


class TestCrossEntityKept:
    def test_cross_entity_same_url_keeps_independent_rows(self) -> None:
        """`cross_entity_kept` — content_hash exists for entity B; ingest
        for entity A → NEW evidence row scoped to A + audit + link."""
        session = FakeSession()
        ev = _Ev(e_id="E-1", excerpt="shared article")
        # Same-entity lookup: nothing. Other-entity: owned by ent-B.
        session.other_rows = [
            _Row(evidence_id="row-for-B", entity_id="ent-B",
                 tier=5, content_hash=_hash_of(ev)),
        ]
        pkg = _Pkg([ev])
        asyncio.run(_persist_evidence(
            session, run_id="run-A", entity_id="ent-A", pkg=pkg,
        ))

        inserts = _find_insert_evidence_rows(session)
        assert len(inserts) == 1
        assert inserts[0]["eid"] == "ent-A"   # new row scoped to A

        audits = _find_audit_rows(session)
        assert len(audits) == 1
        assert audits[0]["act"] == "cross_entity_kept"


class TestTierUpgrade:
    def test_lower_tier_upgrades_existing_row(self) -> None:
        """`tier_upgrade` — incoming tier=3 stronger than existing tier=5;
        UPDATE existing.tier=3; link + audit (reason carries before/after)."""
        session = FakeSession()
        ev = _Ev(e_id="E-1", excerpt="upgrade", tier=3)
        session.same_rows = [
            _Row(evidence_id="existing-1", entity_id="ent-A",
                 tier=5, content_hash=_hash_of(ev)),
        ]
        pkg = _Pkg([ev])
        asyncio.run(_persist_evidence(
            session, run_id="run-2", entity_id="ent-A", pkg=pkg,
        ))

        # Tier UPDATE fires.
        updates = _find_tier_update_rows(session)
        assert len(updates) == 1
        assert updates[0]["new_tier"] == 3
        assert updates[0]["eid"] == "existing-1"

        # No new evidence_index INSERT.
        assert _find_insert_evidence_rows(session) == []

        # Link + audit.
        links = _find_link_rows(session)
        assert len(links) == 1
        assert links[0]["fs"] is False

        audits = _find_audit_rows(session)
        assert len(audits) == 1
        assert audits[0]["act"] == "tier_upgrade"
        # Reason carries before/after info.
        assert "tier=5" in audits[0]["rsn"]
        assert "tier=3" in audits[0]["rsn"]


class TestDuplicateWithinRun:
    def test_duplicate_within_run_is_skipped(self) -> None:
        """`duplicate_within_run` — same content_hash appears twice in
        the same incoming list. First is `kept`; second is
        `duplicate_within_run` and only writes an audit row."""
        session = FakeSession()
        # Two evidence entries with identical (url, claim, excerpt).
        e1 = _Ev(e_id="E-1", excerpt="same body")
        e2 = _Ev(e_id="E-2", excerpt="same body")
        pkg = _Pkg([e1, e2])

        asyncio.run(_persist_evidence(
            session, run_id="run-X", entity_id="ent-A", pkg=pkg,
        ))

        # Exactly one INSERT into evidence_index.
        assert len(_find_insert_evidence_rows(session)) == 1

        # Two audit rows: kept + duplicate_within_run.
        audits = _find_audit_rows(session)
        assert len(audits) == 2
        actions = [a["act"] for a in audits]
        assert actions == ["kept", "duplicate_within_run"]
        # The duplicate's audit points at the kept row's id.
        kept_id = _find_insert_evidence_rows(session)[0]["id"]
        assert audits[1]["ke"] == kept_id


class TestEmpty:
    def test_no_evidence_no_calls(self) -> None:
        session = FakeSession()
        pkg = _Pkg([])
        asyncio.run(_persist_evidence(
            session, run_id="run-1", entity_id="ent-A", pkg=pkg,
        ))
        assert session.calls == []


class _Fact:
    def __init__(self, text: str, claim_label: str | None = None):
        self.text = text
        self.claim_label = claim_label


class TestExcerptFromFacts:
    """2026-07 stress-test fix: 91% of corpus evidence_index.json rows
    carry facts[] but no excerpt — persisted rows must compose the
    excerpt from the top facts instead of the '(no excerpt)' placeholder
    (which capped every AE-facing depth surface at ~15% real excerpts)."""

    def test_excerpt_composed_from_facts(self) -> None:
        session = FakeSession()
        ev = _Ev(e_id="E-9", excerpt="")
        ev.facts = [
            _Fact("Core banking runs on Fiserv DNA since 2019.", "FACT"),
            _Fact("No public API program was found.", "FACT"),
            _Fact("Third fact must not be included.", "FACT"),
        ]
        pkg = _Pkg([ev])
        asyncio.run(_persist_evidence(
            session, run_id="run-1", entity_id="ent-A", pkg=pkg,
        ))
        inserts = _find_insert_evidence_rows(session)
        assert len(inserts) == 1
        exc = inserts[0]["exc"]
        assert exc != "(no excerpt)"
        assert "Fiserv DNA" in exc
        assert "No public API" in exc
        assert "Third fact" not in exc          # only the first 1-2 facts
        assert len(exc) <= 300
        # claim_type falls back to the first fact's claim_label when the
        # row has no signal_direction.
        ev2 = _Ev(e_id="E-10", excerpt="", signal_direction=None)
        ev2.facts = [_Fact("Something observed.", "INFERENCE")]
        s2 = FakeSession()
        asyncio.run(_persist_evidence(
            s2, run_id="run-1", entity_id="ent-A", pkg=_Pkg([ev2]),
        ))
        assert _find_insert_evidence_rows(s2)[0]["ct"] == "INFERENCE"

    def test_placeholder_only_when_facts_absent(self) -> None:
        session = FakeSession()
        ev = _Ev(e_id="E-11", excerpt="")
        ev.facts = [_Fact("   ")]                # whitespace-only fact
        pkg = _Pkg([ev])
        asyncio.run(_persist_evidence(
            session, run_id="run-1", entity_id="ent-A", pkg=pkg,
        ))
        assert _find_insert_evidence_rows(session)[0]["exc"] == "(no excerpt)"

    def test_verbatim_excerpt_still_wins(self) -> None:
        session = FakeSession()
        ev = _Ev(e_id="E-12", excerpt="Verbatim source quote.")
        ev.facts = [_Fact("Fact text that must NOT replace the quote.")]
        pkg = _Pkg([ev])
        asyncio.run(_persist_evidence(
            session, run_id="run-1", entity_id="ent-A", pkg=pkg,
        ))
        assert _find_insert_evidence_rows(session)[0]["exc"] == \
            "Verbatim source quote."

    def test_hash_uses_composed_excerpt(self) -> None:
        """Dedup stability: same facts → same composed excerpt → same
        content hash across runs."""
        ev = _Ev(e_id="E-13", excerpt="")
        ev.facts = [_Fact("Stable fact body.")]
        s1, s2 = FakeSession(), FakeSession()
        asyncio.run(_persist_evidence(
            s1, run_id="run-1", entity_id="ent-A", pkg=_Pkg([ev]),
        ))
        asyncio.run(_persist_evidence(
            s2, run_id="run-2", entity_id="ent-A", pkg=_Pkg([ev]),
        ))
        h1 = _find_insert_evidence_rows(s1)[0]["ch"]
        h2 = _find_insert_evidence_rows(s2)[0]["ch"]
        assert h1 == h2
        assert h1 == compute_content_hash(
            source_url="https://x", claim_type="FACT",
            excerpt="Stable fact body.",
        )
