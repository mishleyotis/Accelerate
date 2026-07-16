"""AE notes on rec cards / roadmap items + the recalibration hook.

New prototype feature (2026-07-06). Recommendation cards and roadmap
items carry an AE-notes segment (migration 061). A note flagged
``recalibrate=True`` is the AE saying "this field intelligence should
change what the DMA concluded" — e.g. "they finished the nCino
migration in June; the P3 workflow gap is stale".

THE HOOK NEVER MUTATES SCORES. It runs a Gemini-backed SIMULATION:
given the note plus the target's real current state (scores, findings,
E-ID-cited evidence excerpts), the model reasons about what WOULD
change — which surfaces, which direction, on what evidence — and the
validated result is stored in ``ae_note_assessments`` for admin review.
Committing any change stays a human decision by design (the mandate:
"deep simulated understanding before any committed change, with full
provenance").

Layering (mirrors focus_area_synthesizer / enrichment):
  - pure, unit-testable pieces: :func:`build_impact_prompt`,
    :func:`parse_assessment_payload`, :func:`validate_assessment`,
    :func:`compose_assessment_md`;
  - async DB assembly: :func:`load_recalibration_context`;
  - the orchestration entry :func:`run_impact_assessment` — called
    best-effort from the notes router; any failure lands as an honest
    FAILED/PENDING assessment row, never a 500 on the note write.

Validation contract (validated-Gemini-only, CLAUDE.md hard rule):
  - every cited E-ID must be inside the grounding bundle we sent;
  - every impact needs non-empty reasoning;
  - impacted surface must come from the closed surface list;
  - any digits in the simulated-change text must appear in the note
    body or the grounding corpus (no fabricated numbers).
On any flag: validators_passed=False, status=FAILED, raw payload kept
for debugging — the admin surface renders only validated assessments.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()

NOTE_TARGET_KINDS = ("recommendation", "roadmap_phase", "insight_card")
NOTE_STATUSES = ("ACTIONED", "PENDING", "SUPERSEDED")

# Closed list of surfaces a simulation may claim impact on. Anything
# else the model invents is a validation flag, not a new capability.
IMPACT_SURFACES = (
    "subcap_score",
    "insight_card",
    "recommendation",
    "platform_fit",
    "focus_area",
    "kpi",
)

_RE_E_ID = re.compile(r"\bE-\d{2,4}\b")
_RE_NUMBER = re.compile(r"\d+(?:\.\d+)?")

PROMPT_VERSION = "ae_note_recalibration_v1"


@dataclass
class RecalibrationContext:
    """Everything the simulation is allowed to reason over."""

    entity_name: str
    target_kind: str
    target_id: str
    target_title: str | None = None
    # [{subcap_id, name, score}] — the target's linked subcap scores.
    subcap_scores: list[dict] = field(default_factory=list)
    # [{e_id, excerpt}] — VERBATIM evidence excerpts (the only E-IDs the
    # model may cite).
    evidence: list[dict] = field(default_factory=list)
    # Extra current-state facts (fit score, phase, outcomes...).
    current_state: dict = field(default_factory=dict)

    @property
    def allowed_e_ids(self) -> set[str]:
        return {str(e.get("e_id")) for e in self.evidence if e.get("e_id")}


def build_impact_prompt(note_body: str, ctx: RecalibrationContext) -> str:
    """Deterministic prompt for the impact SIMULATION. The model is told
    explicitly that it is simulating, not deciding."""
    ev_lines = "\n".join(
        f"- [{e.get('e_id')}] \"{str(e.get('excerpt') or '').strip()}\""
        for e in ctx.evidence[:12]
    ) or "- (no linked evidence rows)"
    score_lines = "\n".join(
        f"- {s.get('subcap_id')} {s.get('name') or ''}: {s.get('score')}"
        for s in ctx.subcap_scores[:12]
    ) or "- (no linked subcap scores)"
    state = json.dumps(ctx.current_state, default=str)[:1200]
    return (
        "You are assessing FIELD INTELLIGENCE from an Account Executive at "
        "Zennify about a client's Digital Maturity Assessment.\n"
        f"Client: {ctx.entity_name}\n"
        f"Target: {ctx.target_kind} {ctx.target_id}"
        + (f" — {ctx.target_title}" if ctx.target_title else "")
        + "\n\n"
        f"AE note (verbatim):\n\"{note_body.strip()}\"\n\n"
        "Current assessment state:\n"
        f"Linked capability scores (1-5 maturity):\n{score_lines}\n"
        f"Evidence on file (E-ID + verbatim excerpt):\n{ev_lines}\n"
        f"Other current values: {state}\n\n"
        "TASK — SIMULATE, do not decide: if this note were verified, which "
        "parts of the assessment would plausibly change? Respond with "
        "strict JSON only:\n"
        "{\n"
        '  "summary": "2-3 sentence plain-English assessment of the note\'s impact",\n'
        '  "impacts": [\n'
        "    {\n"
        f'      "surface": one of {list(IMPACT_SURFACES)},\n'
        '      "target_id": "the subcap/rec/insight/platform id affected",\n'
        '      "current_value": "what the assessment says today",\n'
        '      "simulated_direction": "up" | "down" | "unchanged",\n'
        '      "simulated_change": "what would change and why, in one sentence",\n'
        '      "reasoning": "the causal chain from the note to this change",\n'
        '      "evidence_e_ids": ["E-IDs FROM THE LIST ABOVE that bear on this"],\n'
        '      "requires_verification": "what must be confirmed before committing"\n'
        "    }\n"
        "  ],\n"
        '  "caveats": ["anything the note asserts that the evidence on file contradicts or cannot confirm"]\n'
        "}\n"
        "Rules: cite ONLY E-IDs from the list above; do not invent numbers — "
        "quote figures only from the note or the evidence; if the note "
        "changes nothing, return an empty impacts list and say why in the "
        "summary."
    )


def parse_assessment_payload(raw: str) -> dict | None:
    """Fence-strip + strict-JSON parse. None on malformed output."""
    raw = (raw or "").strip()
    fenced = re.match(r"^```(?:json)?\s*([\s\S]+?)\s*```$", raw)
    if fenced:
        raw = fenced.group(1)
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _numbers_grounded(text_val: str, corpus: str) -> bool:
    """Every number in `text_val` must literally appear in `corpus`
    (the note body + evidence excerpts + current state) — the
    no-fabricated-numbers gate."""
    return all(num in corpus for num in _RE_NUMBER.findall(text_val or ""))


def validate_assessment(
    payload: dict,
    *,
    allowed_e_ids: set[str],
    grounding_corpus: str,
) -> tuple[bool, list[str]]:
    """(ok, flags). Flags name the exact failed gate — persisted into
    ``failure_reason`` so the admin can see WHY a simulation was
    rejected instead of a silent absence."""
    flags: list[str] = []
    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        flags.append("summary_missing")
    impacts = payload.get("impacts")
    if not isinstance(impacts, list):
        flags.append("impacts_not_a_list")
        impacts = []
    for i, imp in enumerate(impacts):
        if not isinstance(imp, dict):
            flags.append(f"impact_{i}_not_object")
            continue
        if imp.get("surface") not in IMPACT_SURFACES:
            flags.append(f"impact_{i}_unknown_surface")
        if not str(imp.get("reasoning") or "").strip():
            flags.append(f"impact_{i}_no_reasoning")
        if imp.get("simulated_direction") not in ("up", "down", "unchanged"):
            flags.append(f"impact_{i}_bad_direction")
        cited = imp.get("evidence_e_ids") or []
        if not isinstance(cited, list):
            flags.append(f"impact_{i}_evidence_not_list")
            cited = []
        for e in cited:
            if str(e) not in allowed_e_ids:
                flags.append(f"impact_{i}_fabricated_e_id:{e}")
        for text_field in ("simulated_change", "current_value"):
            if not _numbers_grounded(str(imp.get(text_field) or ""), grounding_corpus):
                flags.append(f"impact_{i}_ungrounded_number_in_{text_field}")
    # Free-text E-IDs anywhere in the payload must also be real.
    for m in _RE_E_ID.findall(json.dumps(payload)):
        if m not in allowed_e_ids:
            flags.append(f"fabricated_e_id:{m}")
    return (not flags, flags)


def compose_assessment_md(payload: dict, ctx: RecalibrationContext) -> str:
    """Deterministic markdown render of a VALIDATED simulation for the
    admin-review surface. Pure formatting — nothing is added that isn't
    in the validated payload."""
    lines: list[str] = [
        f"**Simulated impact — {ctx.target_kind} {ctx.target_id}"
        + (f" ({ctx.target_title})" if ctx.target_title else "")
        + "**",
        "",
        str(payload.get("summary") or "").strip(),
        "",
    ]
    impacts = payload.get("impacts") or []
    if impacts:
        lines.append("| Surface | Target | Direction | What would change | Evidence |")
        lines.append("|---|---|---|---|---|")
        for imp in impacts:
            if not isinstance(imp, dict):
                continue
            e_ids = ", ".join(str(e) for e in (imp.get("evidence_e_ids") or []))
            lines.append(
                "| {surface} | {target} | {direction} | {change} | {ev} |".format(
                    surface=imp.get("surface", ""),
                    target=imp.get("target_id", ""),
                    direction=imp.get("simulated_direction", ""),
                    change=str(imp.get("simulated_change") or "").replace("|", "/"),
                    ev=e_ids or "—",
                )
            )
        lines.append("")
        for imp in impacts:
            if isinstance(imp, dict) and str(imp.get("requires_verification") or "").strip():
                lines.append(
                    f"- Verify before committing ({imp.get('target_id')}): "
                    f"{imp['requires_verification']}"
                )
    else:
        lines.append("_No assessed impact — the note does not change any current conclusion._")
    caveats = [c for c in (payload.get("caveats") or []) if str(c).strip()]
    if caveats:
        lines.append("")
        lines.append("**Caveats**")
        lines.extend(f"- {c}" for c in caveats)
    lines.append("")
    lines.append(
        "_Simulation only — no score or finding has been changed. "
        "An admin must verify and apply any recalibration explicitly._"
    )
    return "\n".join(line for line in lines if line is not None)


# ── async DB assembly ──────────────────────────────────────────────────


async def load_recalibration_context(
    session: Any,
    *,
    entity_id: str,
    target_kind: str,
    target_id: str,
) -> RecalibrationContext:
    """Assemble the target's REAL current state for the simulation."""
    from sqlalchemy import text

    name_row = (
        await session.execute(
            text("SELECT name FROM entities WHERE id = CAST(:eid AS uuid)"),
            {"eid": str(entity_id)},
        )
    ).first()
    ctx = RecalibrationContext(
        entity_name=(name_row.name if name_row else "the client"),
        target_kind=target_kind,
        target_id=target_id,
    )

    run_row = (
        await session.execute(
            text(
                "SELECT id FROM runs WHERE entity_id = CAST(:eid AS uuid) "
                "AND status = 'ACTIVE' "
                "ORDER BY completed_at DESC NULLS LAST LIMIT 1"
            ),
            {"eid": str(entity_id)},
        )
    ).first()
    if run_row is None:
        return ctx
    run_id = run_row.id

    subcap_ids: list[str] = []
    e_ids: list[str] = []
    if target_kind == "recommendation":
        rec = (
            await session.execute(
                text(
                    """
                    SELECT title, target_subcap_ids, root_cause_e_ids,
                           platform_id, effort_band, phase, outcomes
                    FROM recommendations
                    WHERE run_id = :rid AND rec_id = :tid
                    LIMIT 1
                    """
                ),
                {"rid": run_id, "tid": target_id},
            )
        ).first()
        if rec is not None:
            ctx.target_title = rec.title
            subcap_ids = list(rec.target_subcap_ids or [])
            e_ids = list(rec.root_cause_e_ids or [])
            ctx.current_state = {
                "platform_id": rec.platform_id,
                "effort_band": rec.effort_band,
                "phase": rec.phase,
                "outcomes": rec.outcomes if isinstance(rec.outcomes, dict) else None,
            }
    elif target_kind == "insight_card":
        ic = (
            await session.execute(
                text(
                    """
                    SELECT title, linked_subcap_id, linked_e_ids, severity
                    FROM insight_cards
                    WHERE run_id = :rid AND ic_id = :tid
                    LIMIT 1
                    """
                ),
                {"rid": run_id, "tid": target_id},
            )
        ).first()
        if ic is not None:
            ctx.target_title = ic.title
            subcap_ids = [ic.linked_subcap_id] if ic.linked_subcap_id else []
            e_ids = list(ic.linked_e_ids or [])
            ctx.current_state = {"severity": ic.severity}
    elif target_kind == "roadmap_phase":
        # phase-N → the phase's recommendations define the scope.
        m = re.search(r"(\d+)", target_id)
        phase_n = int(m.group(1)) if m else None
        if phase_n is not None:
            recs = (
                await session.execute(
                    text(
                        """
                        SELECT rec_id, title, target_subcap_ids, root_cause_e_ids
                        FROM recommendations
                        WHERE run_id = :rid AND phase = :ph
                        ORDER BY rec_id
                        """
                    ),
                    {"rid": run_id, "ph": phase_n},
                )
            ).all()
            ctx.target_title = f"Roadmap phase {phase_n}"
            ctx.current_state = {
                "recommendations": [
                    {"rec_id": r.rec_id, "title": r.title} for r in recs
                ]
            }
            for r in recs:
                subcap_ids.extend(list(r.target_subcap_ids or []))
                e_ids.extend(list(r.root_cause_e_ids or []))

    subcap_ids = list(dict.fromkeys(subcap_ids))[:12]
    e_ids = list(dict.fromkeys(e_ids))[:12]

    if subcap_ids:
        score_rows = (
            await session.execute(
                text(
                    """
                    SELECT s.subcap_id, s.score, cs.name
                    FROM subcap_scores s
                    LEFT JOIN ccg_subcaps cs
                      ON cs.subcap_id = s.subcap_id AND cs.version = 'v7.0'
                    WHERE s.run_id = :rid AND s.subcap_id = ANY(:sids)
                    """
                ),
                {"rid": run_id, "sids": subcap_ids},
            )
        ).all()
        ctx.subcap_scores = [
            {
                "subcap_id": r.subcap_id,
                "name": r.name,
                "score": float(r.score) if r.score is not None else None,
            }
            for r in score_rows
        ]

    # Evidence: the target's cited E-IDs first, then subcap-linked rows.
    ev_rows = (
        await session.execute(
            text(
                """
                SELECT e_id, excerpt FROM evidence_index
                WHERE run_id = :rid AND (
                    e_id = ANY(:eids)
                    OR linked_subcap_ids && CAST(:sids AS varchar[])
                )
                ORDER BY (e_id = ANY(:eids)) DESC, tier ASC NULLS LAST, e_id
                LIMIT 12
                """
            ),
            {"rid": run_id, "eids": e_ids or [""], "sids": subcap_ids or [""]},
        )
    ).all()
    ctx.evidence = [
        {"e_id": r.e_id, "excerpt": (r.excerpt or "")[:400]} for r in ev_rows
    ]
    return ctx


async def run_impact_assessment(
    session: Any,
    *,
    note_id: str,
    entity_id: str,
    target_kind: str,
    target_id: str,
    note_body: str,
) -> dict:
    """Run one simulation for a recalibrate note; UPSERT the assessment
    row. Returns {status, assessment_id}. Never raises — every failure
    mode is an honest status on the row."""
    from sqlalchemy import text

    ctx = await load_recalibration_context(
        session,
        entity_id=entity_id,
        target_kind=target_kind,
        target_id=target_id,
    )
    prompt = build_impact_prompt(note_body, ctx)

    status = "FAILED"
    assessment_md: str | None = None
    impact_json: dict | None = None
    validators_passed = False
    failure_reason: str | None = None
    model_used: str | None = None

    raw: str | None = None
    try:
        from app.services.vertex_client import GeminiCall, get_vertex_client

        client = get_vertex_client()
        buf: list[str] = []
        async for chunk in client.stream(
            GeminiCall(
                surface="ae_note_recalibration",
                model="flash",
                prompt=prompt,
                max_output_tokens=4096,
                temperature=0.2,
            )
        ):
            buf.append(chunk)
        raw = "".join(buf).strip()
        model_used = "gemini-flash"
    except Exception as e:  # offline / creds / stream failure — honest PENDING
        status = "PENDING"
        failure_reason = f"gemini_unavailable: {type(e).__name__}: {str(e)[:200]}"
        log.warning("ae_notes.assessment_gemini_unavailable", note_id=note_id,
                    err=str(e)[:200])

    if raw is not None:
        payload = parse_assessment_payload(raw)
        if payload is None:
            failure_reason = "malformed_json"
        else:
            corpus = " ".join(
                [note_body]
                + [str(e.get("excerpt") or "") for e in ctx.evidence]
                + [json.dumps(ctx.current_state, default=str)]
                + [json.dumps(ctx.subcap_scores, default=str)]
            )
            ok, flags = validate_assessment(
                payload,
                allowed_e_ids=ctx.allowed_e_ids,
                grounding_corpus=corpus,
            )
            impact_json = payload
            if ok:
                status = "SIMULATED"
                validators_passed = True
                assessment_md = compose_assessment_md(payload, ctx)
            else:
                failure_reason = "validator_flags: " + "; ".join(flags[:10])

    row = (
        await session.execute(
            text(
                """
                INSERT INTO ae_note_assessments
                  (note_id, status, assessment_md, impact, model,
                   grounding_evidence_ids, validators_passed, failure_reason)
                VALUES
                  (CAST(:nid AS uuid), :status, :md, CAST(:impact AS jsonb),
                   :model, CAST(:geids AS text[]), :vp, :fail)
                RETURNING id
                """
            ),
            {
                "nid": str(note_id),
                "status": status,
                "md": assessment_md,
                "impact": json.dumps(impact_json) if impact_json is not None else None,
                "model": model_used,
                "geids": sorted(ctx.allowed_e_ids),
                "vp": validators_passed,
                "fail": failure_reason,
            },
        )
    ).first()
    return {"status": status, "assessment_id": str(row.id) if row else None}
