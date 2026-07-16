"""Section routing — which DMA report section feeds which UI surface.

The 12 canonical report sections are listed in PRD §02. Each ingested
`document_sections` row's `section_kind` determines which surface picks it
up. Renderers query this map to find the relevant section for a surface
and degrade gracefully (with the documented empty state) when none exists.

State-branch contract (for the runtime `build_narrative_*` helpers):
  - lineage_complete  → DOCX parsed, all expected sections present →
                         every surface gets a populated bundle.
  - lineage_partial   → DOCX parsed but some kinds missing → present
                         keys populated; absent keys returned as None
                         so the frontend keeps showing the skeleton.
  - lineage_empty     → no DOCX → bundle returns None at the top level;
                         the endpoint sets `narrative: null`.
  - alias_resolved    → a section mentions a subcap_id that resolves
                         through ccg_subcap_aliases; the lineage table
                         is keyed by the *resolved* current-version ID
                         so reverse lookups still match.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.text_hygiene import scrub_md

SectionKind = Literal[
    "executive_summary_scqa",
    "trend_analysis",
    "issue_register",
    "pillar_deep_dive_p1",
    "pillar_deep_dive_p2",
    "pillar_deep_dive_p3",
    "pillar_deep_dive_p4",
    "benchmark_comparison",
    "gap_prioritization",
    "recommendations",
    "roadmap",
    "data_gaps",
    "evidence_registry",
]

Surface = Literal[
    "D1_overview",
    "D2_insights",
    "D3_heatmap",
    "D4_platform",
    "D5_context",
    "D6_health",
    "evidence_drawer",
]


# Each row: section → ordered list of surfaces that consume it.
SECTION_TO_SURFACES: dict[SectionKind, list[Surface]] = {
    "executive_summary_scqa":     ["D1_overview"],
    "trend_analysis":             ["D5_context"],
    "issue_register":             ["D3_heatmap", "D5_context"],
    "pillar_deep_dive_p1":        ["D2_insights", "D3_heatmap"],
    "pillar_deep_dive_p2":        ["D2_insights", "D3_heatmap"],
    "pillar_deep_dive_p3":        ["D2_insights", "D3_heatmap"],
    "pillar_deep_dive_p4":        ["D2_insights", "D3_heatmap"],
    "benchmark_comparison":       ["D3_heatmap", "D1_overview"],
    "gap_prioritization":         ["D4_platform", "D1_overview"],
    "recommendations":            ["D4_platform", "D2_insights"],
    "roadmap":                    ["D4_platform"],
    "data_gaps":                  ["D6_health"],
    "evidence_registry":          ["evidence_drawer"],
}


# Reverse index, useful for renderers.
def sections_for_surface(surface: Surface) -> list[SectionKind]:
    return sorted(
        section for section, surfaces in SECTION_TO_SURFACES.items()
        if surface in surfaces
    )


def surfaces_for_section(section: SectionKind) -> list[Surface]:
    return list(SECTION_TO_SURFACES.get(section, []))


# ----------------------------------------------------------------------
# Runtime narrative bundle helpers
# ----------------------------------------------------------------------

@dataclass
class SectionPayload:
    """A single section's narrative payload — the shape every surface
    consumes. `body_md` is the analyst's prose; `linked_subcap_ids` and
    `linked_e_ids` are derived from `document_lineage` so the UI can
    cross-reference cells / drawer items.
    """
    kind: str
    heading: str
    body_md: str
    page_number: int | None = None
    linked_subcap_ids: list[str] = field(default_factory=list)
    linked_e_ids: list[str] = field(default_factory=list)
    linked_pillar_ids: list[str] = field(default_factory=list)


_MD_META_LINE = re.compile(
    r"^\s*(#{1,6}\s*(Report Synthesis|Assessment ID|Generated)\b.*"
    r"|Assessment\s+ID\s*:.*"
    r"|Generated\s*:\s*[\d-]{4,}.*"
    r"|-{3,}\s*)$",
    re.IGNORECASE,
)
_MD_HEADING = re.compile(r"^\s*#{1,6}\s*")


def _strip_pipeline_metadata(body: str) -> str:
    """Presentation hygiene for narrative bodies (2026-06-10 parity
    click-through): `report_synthesis.md` ships with bot pipeline
    headers — "# Report Synthesis — <client> DMA", "## Assessment ID:
    DMA-ASM-…", "## Generated: 2026-03-18T10:54:30.141481", "---"
    rules — which rendered VERBATIM at the top of every Executive
    narrative card. Drop metadata lines entirely and de-tokenize the
    remaining markdown headings (the frontend renders narrative text
    as plain prose, so literal `##` is noise). Content lines are never
    removed."""
    out: list[str] = []
    for line in (body or "").splitlines():
        if _MD_META_LINE.match(line):
            continue
        out.append(_MD_HEADING.sub("", line))
    cleaned = "\n".join(out).strip()
    # The narrative cards render PLAIN prose — de-tokenize residual
    # markdown emphasis so "**2.31**" doesn't show literal asterisks.
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)
    return cleaned or (body or "")


async def load_sections_for_run(
    session: AsyncSession, run_id: Any, entity_id: Any | None = None,
) -> list[SectionPayload]:
    """Load every document_sections row for a run plus its lineage refs.

    ``entity_id`` (2026-06-10 cross-wire defense): document_sections
    snapshots the OWNING entity at persist time. On the live app, a
    run mis-attached to the wrong entity (SYNTH-run-id / display_id
    collisions in earlier ingests) served ANOTHER institution's SCQA on
    an unrelated client's Overview ("CU" rendering FNBO's narrative).
    When the caller passes the page's entity_id, the lookup can only
    ever return sections persisted FOR that entity — a mis-attached
    run yields an empty narrative (honest skeleton) instead of someone
    else's prose. All router call sites pass it; None preserves the
    legacy run-only behavior for internal tooling.
    """
    rows = (await session.execute(
        text(
            """
            SELECT ds.id, ds.section_kind, ds.heading, ds.body, ds.page_number
            FROM document_sections ds
            WHERE ds.run_id = :rid
              AND (CAST(:eid AS uuid) IS NULL
                   OR ds.entity_id = CAST(:eid AS uuid))
            ORDER BY ds.ordinal
            """
        ),
        {"rid": run_id, "eid": str(entity_id) if entity_id else None},
    )).all()
    if not rows:
        return []

    section_ids = [r.id for r in rows]
    lineage = (await session.execute(
        text(
            """
            SELECT section_id, target_type, target_ref
            FROM document_lineage
            WHERE section_id = ANY(:sids)
            """
        ),
        {"sids": section_ids},
    )).all()
    # Citation-validity floor (2026-07-11, build 5d3f7f78 parity audit):
    # lineage E-IDs are parsed from analyst PROSE, and reports cite E-IDs
    # that never shipped in the package's evidence_index (Guaranteed Rate
    # cites E-143/E-144 against a 142-row index). A dangling id renders a
    # dead citation chip (the drawer can never resolve it), and the pack
    # fixer (apply_startup_data_fixes) already prunes them from the BAKED
    # pack — so the live route must apply the SAME floor or qa_pack_parity
    # structurally diffs pack vs live. Mirror the fixer's guard exactly:
    # an EMPTY evidence set (hollow package) disables the filter.
    known_eids = {
        r.e_id for r in (await session.execute(
            text("SELECT DISTINCT e_id FROM evidence_index WHERE run_id = :rid"),
            {"rid": run_id},
        )).all()
    }
    by_section: dict[Any, dict[str, list[str]]] = {}
    for lr in lineage:
        bucket = by_section.setdefault(
            lr.section_id,
            {"subcap_id": [], "e_id": [], "pillar_id": []},
        )
        if lr.target_type in bucket:
            bucket[lr.target_type].append(lr.target_ref)

    out: list[SectionPayload] = []
    for r in rows:
        b = by_section.get(
            r.id, {"subcap_id": [], "e_id": [], "pillar_id": []},
        )
        out.append(SectionPayload(
            kind=r.section_kind,
            heading=r.heading or "",
            body_md=_strip_pipeline_metadata(r.body or ""),
            page_number=r.page_number,
            linked_subcap_ids=sorted(set(b.get("subcap_id", []))),
            linked_e_ids=sorted(
                (set(b.get("e_id", [])) & known_eids) if known_eids
                else set(b.get("e_id", []))
            ),
            linked_pillar_ids=sorted(set(b.get("pillar_id", []))),
        ))
    return out


def _first_of_kind(sections: list[SectionPayload], kind: str) -> SectionPayload | None:
    """First section of `kind` with a NON-EMPTY body, else the first of
    the kind at all. 13 corpus packages (2026-06-10 census) carry a
    heading-only duplicate BEFORE the real section in DOCX ordinal
    order (e.g. Zions ships an empty `executive_summary_scqa` row at
    ordinal 0 and the 2k-char one later) — preferring by ordinal alone
    blanked the D1 narrative for all of them."""
    fallback: SectionPayload | None = None
    for s in sections:
        if s.kind == kind:
            if s.body_md.strip():
                return s
            if fallback is None:
                fallback = s
    return fallback


# ----------------------------------------------------------------------
# Per-surface bundle builders. Each returns None when no lineage rows are
# available for that surface — the endpoint then emits `narrative: null`.
# ----------------------------------------------------------------------

def build_narrative_overview(sections: list[SectionPayload]) -> dict[str, Any] | None:
    """D1 Overview narrative bundle: SCQA + benchmark + gap prioritization."""
    scqa_sec = _first_of_kind(sections, "executive_summary_scqa")
    bench = _first_of_kind(sections, "benchmark_comparison")
    gap = _first_of_kind(sections, "gap_prioritization")
    if not any((scqa_sec, bench, gap)):
        return None
    bundle: dict[str, Any] = {}
    if scqa_sec:
        bundle["scqa_md"] = scrub_md(scqa_sec.body_md)
        # The DOCX heading is served verbatim ("Report Synthesis —
        # DMA-ASM-ALMA-20260519-0001") — scrub the run-id / jargon out of it
        # too (2026-07-14 vet). plain() is the single-line scrubber.
        from app.services.text_hygiene import plain as _plain
        bundle["scqa_heading"] = _plain(scqa_sec.heading) or scqa_sec.heading
        bundle["page_number"] = scqa_sec.page_number
    if bench:
        bundle["benchmark_md"] = scrub_md(bench.body_md)
    if gap:
        bundle["gap_prioritization_md"] = scrub_md(gap.body_md)
    return bundle


def build_narrative_insights(sections: list[SectionPayload]) -> dict[str, Any] | None:
    """D2 Insights narrative: per-pillar deep-dive + recommendations."""
    per_pillar: dict[str, dict[str, Any]] = {}
    for pillar_n in (1, 2, 3, 4):
        kind = f"pillar_deep_dive_p{pillar_n}"
        sec = _first_of_kind(sections, kind)
        if sec:
            per_pillar[f"P{pillar_n}"] = {
                "findings_md": scrub_md(sec.body_md),
                "heading": sec.heading,
                "linked_subcap_ids": sec.linked_subcap_ids,
                "linked_e_ids": sec.linked_e_ids,
            }
    recs = _first_of_kind(sections, "recommendations")
    if not per_pillar and recs is None:
        return None
    return {
        "per_pillar": per_pillar or None,
        "recommendations_md": scrub_md(recs.body_md) if recs else None,
    }


def build_narrative_heatmap(
    sections: list[SectionPayload],
    *,
    llm_narratives: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """D3 Heatmap narrative: per-pillar rationale + benchmark + issue register.

    ``llm_narratives`` (optional) is a dict
    ``{subcap_id: {"narrative_md": "...", "evidence_anchors": [...],
                    "confidence": float, "data_source": "llm"}}``
    populated by ``parsers.subcap_narrative_extractor.extract_per_subcap_narrative``
    when the run has been processed by the structured-output classifier.
    When present, it OVERRIDES the regex paragraph-split for any subcap_id
    it covers. Subcaps the LLM didn't cover fall back to the heuristic.

    The output dict gains ``per_subcap_meta`` ({subcap_id: data_source})
    so the UI can render ``data-source="llm"|"heuristic"`` on each cell.
    """
    per_pillar: dict[str, str] = {}
    per_subcap: dict[str, str] = {}
    per_subcap_meta: dict[str, str] = {}
    llm = llm_narratives or {}

    for pillar_n in (1, 2, 3, 4):
        kind = f"pillar_deep_dive_p{pillar_n}"
        sec = _first_of_kind(sections, kind)
        if sec:
            per_pillar[f"P{pillar_n}"] = sec.body_md
            for sid in sec.linked_subcap_ids:
                # Prefer the LLM narrative when present.
                llm_entry = llm.get(sid)
                if llm_entry and llm_entry.get("narrative_md"):
                    per_subcap.setdefault(sid, llm_entry["narrative_md"])
                    per_subcap_meta[sid] = llm_entry.get("data_source", "llm")
                else:
                    paragraphs = [p for p in sec.body_md.split("\n\n") if sid in p]
                    if paragraphs:
                        per_subcap.setdefault(sid, "\n\n".join(paragraphs))
                        per_subcap_meta[sid] = "heuristic"
    bench = _first_of_kind(sections, "benchmark_comparison")
    issues = _first_of_kind(sections, "issue_register")
    if not per_pillar and bench is None and issues is None:
        return None
    # Scrub the OUTPUT values (not the raw bodies above): the per_subcap
    # split keys on the P#C# codes as delimiters, so it must run on raw
    # text first; the served narratives are then jargon-stripped and
    # proofread (idempotent typography + analyst shout-note cleanup —
    # the DOCX deep-dive bodies are the drawer's dominant text source).
    from app.services.nlp.quality import proofread

    def _serve(v: str | None) -> str | None:
        s = scrub_md(v)
        return (proofread(s) or s) if s else s

    return {
        "per_pillar_md": {k: _serve(v) for k, v in per_pillar.items()} or None,
        "per_subcap_md": {k: _serve(v) for k, v in per_subcap.items()} or None,
        "per_subcap_meta": per_subcap_meta or None,
        "benchmark_md": _serve(bench.body_md) if bench else None,
        "issue_register_md": _serve(issues.body_md) if issues else None,
    }


def build_narrative_platform(sections: list[SectionPayload]) -> dict[str, Any] | None:
    """D4 Platform narrative: recommendations + roadmap + gap prioritization."""
    recs = _first_of_kind(sections, "recommendations")
    roadmap = _first_of_kind(sections, "roadmap")
    gap = _first_of_kind(sections, "gap_prioritization")
    if not any((recs, roadmap, gap)):
        return None
    return {
        "recommendations_md": scrub_md(recs.body_md) if recs else None,
        "roadmap_md": scrub_md(roadmap.body_md) if roadmap else None,
        "gap_prioritization_md": scrub_md(gap.body_md) if gap else None,
    }


def build_narrative_context(sections: list[SectionPayload]) -> dict[str, Any] | None:
    """D5 Context narrative: trend analysis + issue register."""
    trend = _first_of_kind(sections, "trend_analysis")
    issues = _first_of_kind(sections, "issue_register")
    if trend is None and issues is None:
        return None
    return {
        "trend_md": scrub_md(trend.body_md) if trend else None,
        "issue_register_md": scrub_md(issues.body_md) if issues else None,
    }


def build_narrative_health(sections: list[SectionPayload]) -> dict[str, Any] | None:
    """D6 Health narrative: data gaps + evidence registry preface."""
    gaps = _first_of_kind(sections, "data_gaps")
    reg = _first_of_kind(sections, "evidence_registry")
    if gaps is None and reg is None:
        return None
    return {
        "data_gaps_md": scrub_md(gaps.body_md) if gaps else None,
        "evidence_registry_preface_md": scrub_md(reg.body_md) if reg else None,
    }


def narrative_state(sections: list[SectionPayload]) -> str:
    """State-transition label for logging/tests.

    Returns one of `lineage_empty | lineage_partial | lineage_complete`
    based on the fraction of EXPECTED_KINDS present.
    """
    if not sections:
        return "lineage_empty"
    kinds = {s.kind for s in sections}
    expected = {
        "executive_summary_scqa", "trend_analysis", "issue_register",
        "pillar_deep_dive_p1", "pillar_deep_dive_p2",
        "pillar_deep_dive_p3", "pillar_deep_dive_p4",
        "benchmark_comparison", "gap_prioritization",
        "recommendations", "roadmap", "data_gaps",
    }
    coverage = len(kinds & expected) / len(expected)
    if coverage >= 0.80:
        return "lineage_complete"
    return "lineage_partial"
