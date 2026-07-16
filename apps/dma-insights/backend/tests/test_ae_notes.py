"""AE notes + recalibration hook (migration 057) — pure-logic contract.

The hook SIMULATES impact and stores it for admin review; it never
mutates scores. These tests pin:
  - the prompt carries the note verbatim, the real current state, and
    the simulate-don't-decide instruction;
  - validation is fail-closed: fabricated E-IDs, ungrounded numbers,
    unknown surfaces, missing reasoning all flag;
  - the markdown render is deterministic and carries the
    "no score has been changed" provenance line;
  - closed vocabularies match the migration CHECK constraints;
  - the router's write path inserts with the author identity and the
    recalibrate flag, and the assessment endpoint never leaks an
    unvalidated payload.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.ae_notes import (
    IMPACT_SURFACES,
    NOTE_STATUSES,
    NOTE_TARGET_KINDS,
    RecalibrationContext,
    build_impact_prompt,
    compose_assessment_md,
    parse_assessment_payload,
    validate_assessment,
)


def _ctx() -> RecalibrationContext:
    return RecalibrationContext(
        entity_name="Alma Bank",
        target_kind="recommendation",
        target_id="REC-08",
        target_title="Deploy Data Cloud identity resolution",
        subcap_scores=[
            {"subcap_id": "P4C1.1.1", "name": "Data foundation", "score": 1.8},
        ],
        evidence=[
            {"e_id": "E-047", "excerpt": "The firm has no CDP; profiles are stitched manually."},
            {"e_id": "E-101", "excerpt": "Loan origination cycle is 12 days median."},
        ],
        current_state={"platform_id": "salesforce", "phase": 2},
    )


def _valid_payload() -> dict:
    return {
        "summary": "The note reports the CDP gap has been closed since the assessment.",
        "impacts": [
            {
                "surface": "subcap_score",
                "target_id": "P4C1.1.1",
                "current_value": "1.8",
                "simulated_direction": "up",
                "simulated_change": "Data foundation would no longer sit at 1.8 if the CDP deployment is verified.",
                "reasoning": "The note contradicts E-047 (no CDP); a deployed CDP removes the root cause of the 1.8 score.",
                "evidence_e_ids": ["E-047"],
                "requires_verification": "Confirm the CDP go-live date and scope.",
            }
        ],
        "caveats": ["Evidence on file (E-047) still states no CDP exists."],
    }


# ── prompt ─────────────────────────────────────────────────────────────

def test_prompt_carries_note_verbatim_and_simulation_frame():
    note = "They deployed Segment CDP in June; the profile-stitching gap is stale."
    prompt = build_impact_prompt(note, _ctx())
    assert note in prompt
    assert "SIMULATE, do not decide" in prompt
    assert "E-047" in prompt and "E-101" in prompt
    assert "P4C1.1.1" in prompt and "1.8" in prompt
    assert "Alma Bank" in prompt
    assert "do not invent numbers" in prompt


# ── parse ──────────────────────────────────────────────────────────────

def test_parse_strips_markdown_fence():
    import json
    raw = "```json\n" + json.dumps(_valid_payload()) + "\n```"
    assert parse_assessment_payload(raw) == _valid_payload()


def test_parse_rejects_garbage():
    assert parse_assessment_payload("not json at all") is None
    assert parse_assessment_payload("[1, 2, 3]") is None
    assert parse_assessment_payload("") is None


# ── validate ───────────────────────────────────────────────────────────

def _corpus(note: str = "They deployed a CDP in June.") -> str:
    ctx = _ctx()
    import json
    return " ".join(
        [note]
        + [e["excerpt"] for e in ctx.evidence]
        + [json.dumps(ctx.current_state), json.dumps(ctx.subcap_scores)]
    )


def test_valid_payload_passes():
    ok, flags = validate_assessment(
        _valid_payload(), allowed_e_ids={"E-047", "E-101"},
        grounding_corpus=_corpus(),
    )
    assert ok, flags


def test_fabricated_e_id_flags():
    p = _valid_payload()
    p["impacts"][0]["evidence_e_ids"] = ["E-999"]
    ok, flags = validate_assessment(
        p, allowed_e_ids={"E-047"}, grounding_corpus=_corpus(),
    )
    assert not ok
    assert any("fabricated_e_id" in f for f in flags)


def test_ungrounded_number_flags():
    p = _valid_payload()
    p["impacts"][0]["simulated_change"] = "Score would jump to 4.7 immediately."
    ok, flags = validate_assessment(
        p, allowed_e_ids={"E-047", "E-101"}, grounding_corpus=_corpus(),
    )
    assert not ok
    assert any("ungrounded_number" in f for f in flags)


def test_number_from_note_or_evidence_is_grounded():
    p = _valid_payload()
    # 12 appears in E-101's excerpt — allowed.
    p["impacts"][0]["simulated_change"] = (
        "The 12 day origination cycle claim would need re-measurement."
    )
    ok, flags = validate_assessment(
        p, allowed_e_ids={"E-047", "E-101"}, grounding_corpus=_corpus(),
    )
    assert ok, flags


def test_unknown_surface_and_missing_reasoning_flag():
    p = _valid_payload()
    p["impacts"][0]["surface"] = "stock_price"
    p["impacts"][0]["reasoning"] = ""
    ok, flags = validate_assessment(
        p, allowed_e_ids={"E-047"}, grounding_corpus=_corpus(),
    )
    assert not ok
    assert any("unknown_surface" in f for f in flags)
    assert any("no_reasoning" in f for f in flags)


def test_empty_impacts_is_valid_when_note_changes_nothing():
    p = {"summary": "The note restates what E-047 already says; nothing changes.",
         "impacts": [], "caveats": []}
    ok, flags = validate_assessment(
        p, allowed_e_ids={"E-047"}, grounding_corpus=_corpus(),
    )
    assert ok, flags


# ── markdown render ────────────────────────────────────────────────────

def test_markdown_carries_simulation_only_provenance():
    md = compose_assessment_md(_valid_payload(), _ctx())
    assert "Simulation only — no score or finding has been changed" in md
    assert "REC-08" in md
    assert "E-047" in md
    assert "Verify before committing" in md
    assert "Evidence on file (E-047) still states no CDP exists." in md


def test_markdown_empty_impacts_is_honest():
    md = compose_assessment_md(
        {"summary": "No change.", "impacts": [], "caveats": []}, _ctx(),
    )
    assert "No assessed impact" in md


# ── closed vocabularies match migration 061 CHECKs ─────────────────────

def test_vocabularies_match_migration_061():
    from pathlib import Path
    mig = (
        Path(__file__).resolve().parents[1]
        / "alembic" / "versions" / "061_ae_notes.py"
    ).read_text(encoding="utf-8")
    for kind in NOTE_TARGET_KINDS:
        assert f"'{kind}'" in mig
    for st in NOTE_STATUSES:
        assert f"'{st}'" in mig
    assert "061_ae_notes" in mig and "060_kpi_evidence_trace" in mig


def test_impact_surfaces_are_closed_and_known():
    assert set(IMPACT_SURFACES) == {
        "subcap_score", "insight_card", "recommendation",
        "platform_fit", "focus_area", "kpi",
    }


# ── router write path (fake session) ───────────────────────────────────

class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Result:
    def __init__(self, rows):
        self._rows = rows or []

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []
        self.committed = 0

    async def execute(self, sql, params=None):
        self.calls.append((str(sql), dict(params or {})))
        if self.responses:
            return _Result(self.responses.pop(0))
        return _Result([])

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        pass


class _User:
    def __init__(self, role="AE"):
        self.user_id = "u1"
        self.email = "mishley.otiende@zennify.com"
        self.role = role


_ENT = str(uuid4())
_RUN = str(uuid4())
_NOTE = str(uuid4())

from datetime import UTC, datetime  # noqa: E402


def _note_row(recal=False):
    return _Row(
        id=_NOTE, target_kind="recommendation", target_id="REC-08",
        author_email="mishley.otiende@zennify.com", author_role="AE",
        status="PENDING", body="Client confirmed nCino go-live slipped to Q4.",
        sf_opp_id=None, recalibrate=recal,
        created_at=datetime.now(UTC),
    )


def test_create_note_inserts_author_identity():
    from app.routers.notes import NoteIn, create_note

    session = FakeSession([
        [_Row(id=_ENT)],          # entity
        [_Row(id=_RUN)],          # active run
        [_note_row()],            # insert returning
    ])
    out = asyncio.run(create_note(
        "alma-bank",
        NoteIn(target_kind="recommendation", target_id="REC-08",
               body="Client confirmed nCino go-live slipped to Q4."),
        _User(), session,
    ))
    assert out.author_email == "mishley.otiende@zennify.com"
    assert out.author_role == "AE"
    assert out.assessment_status is None  # no recalibration requested
    insert_sql, insert_params = session.calls[2]
    assert "INSERT INTO ae_notes" in insert_sql
    assert insert_params["recal"] is False
    assert session.committed == 1


def test_customer_role_is_403():
    from app.routers.notes import NoteIn, create_note

    session = FakeSession([])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_note(
            "alma-bank",
            NoteIn(target_kind="recommendation", target_id="REC-08", body="x"),
            _User(role="CUSTOMER"), session,
        ))
    assert exc.value.status_code == 403
    assert session.calls == []  # gate fires before any query


def test_assessment_endpoint_never_leaks_unvalidated_payload():
    from app.routers.notes import get_note_assessment

    session = FakeSession([
        [_Row(
            id=str(uuid4()), note_id=_NOTE, status="FAILED",
            assessment_md="RAW UNVALIDATED", impact={"impacts": [{"surface": "x"}]},
            model="gemini-flash", grounding_evidence_ids=["E-047"],
            validators_passed=False,
            failure_reason="validator_flags: fabricated_e_id:E-999",
            created_at=datetime.now(UTC), reviewed_by=None, reviewed_at=None,
        )],
    ])
    out = asyncio.run(get_note_assessment(_NOTE, _User(), session))
    assert out.status == "FAILED"
    assert out.assessment_md is None      # fail-closed
    assert out.impact is None             # fail-closed
    assert out.failure_reason.startswith("validator_flags")
    assert out.grounding_evidence_ids == ["E-047"]


def test_recalibrate_note_records_assessment_status(monkeypatch):
    from app.routers import notes as notes_router
    from app.routers.notes import NoteIn, create_note

    async def _fake_assess(session, **kw):
        return {"status": "SIMULATED", "assessment_id": str(uuid4())}

    monkeypatch.setattr(notes_router, "run_impact_assessment", _fake_assess)
    session = FakeSession([
        [_Row(id=_ENT)],
        [_Row(id=_RUN)],
        [_note_row(recal=True)],
    ])
    out = asyncio.run(create_note(
        "alma-bank",
        NoteIn(target_kind="recommendation", target_id="REC-08",
               body="Client confirmed nCino go-live slipped to Q4.",
               recalibrate=True),
        _User(), session,
    ))
    assert out.recalibrate is True
    assert out.assessment_status == "SIMULATED"


def test_note_write_survives_assessment_crash(monkeypatch):
    from app.routers import notes as notes_router
    from app.routers.notes import NoteIn, create_note

    async def _boom(session, **kw):
        raise RuntimeError("vertex exploded")

    monkeypatch.setattr(notes_router, "run_impact_assessment", _boom)
    session = FakeSession([
        [_Row(id=_ENT)],
        [_Row(id=_RUN)],
        [_note_row(recal=True)],
    ])
    out = asyncio.run(create_note(
        "alma-bank",
        NoteIn(target_kind="recommendation", target_id="REC-08",
               body="x", recalibrate=True),
        _User(), session,
    ))
    assert out.id == _NOTE               # the note itself landed
    assert out.assessment_status is None  # honest: no assessment recorded
