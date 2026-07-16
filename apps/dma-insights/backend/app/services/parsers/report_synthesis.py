"""Parse `report_synthesis.md` → the D1 Overview SCQA narrative.

`report_synthesis.md` (41 packages) is the bot's rendered 4-part SCQA —
"Generated from report_analysis.json, EVERY claim cites specific E-IDs" —
with a fixed body:

    ## 1. What story does the DATA tell?        (Situation)
    ## 2. … complication / peer gaps …          (Complication)
    ## 3. … what to prioritise …                (Question)
    ## 4. … cross-pillar unlocks …              (Answer)

It is currently unread. The D1 SCQA card (`section_routing.
build_narrative_overview`) renders `scqa_md` from a section of kind
`executive_summary_scqa` — sourced today only from the Assessment Report
DOCX. This parser lets `report_synthesis.md` feed that SAME channel as a
`ReportSectionRow`, so it flows through the existing
`document_sections → section_routing → narrative` pipeline with no new
endpoint/FE wiring. Used only when the DOCX did not already supply an
executive_summary_scqa section (additive).

Pure / no DB. Returns None when the file is absent / empty.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_E_ID_RE = re.compile(r"\bE-\d{1,4}\b")
# Catalogue category / subcap ids: P3C3, P4C2, P1C1.1.2 …
_SUBCAP_RE = re.compile(r"\bP\d+C\d+(?:\.\d+)*\b")
# Candidate filenames in priority order across the folders that ship it.
REPORT_SYNTHESIS_NAMES = ("report_synthesis.md",)
REPORT_SYNTHESIS_DIRS = ("02_research_workbook", "04_reports", "08_appendices")


@dataclass
class ReportSynthesis:
    body: str
    heading: str
    e_ids: list[str] = field(default_factory=list)
    subcap_ids: list[str] = field(default_factory=list)


def parse_report_synthesis_md(path: Path) -> ReportSynthesis | None:
    """Read `report_synthesis.md` → body + extracted E-IDs / subcap ids
    for lineage. Returns None when the file is absent or has no real prose.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text()
    except OSError:
        return None
    stripped = text.strip()
    # Require some real body beyond the boilerplate "Generated from …" line.
    if len(stripped) < 80:
        return None

    # Heading: first level-1 ATX heading, else a stable default.
    heading = "Report Synthesis"
    for line in stripped.splitlines():
        if line.startswith("# "):
            heading = line.lstrip("# ").strip() or heading
            break

    e_ids = sorted(set(_E_ID_RE.findall(text)))
    subcap_ids = sorted(set(_SUBCAP_RE.findall(text)))
    return ReportSynthesis(
        body=stripped,
        heading=heading[:300],
        e_ids=e_ids,
        subcap_ids=subcap_ids,
    )


def build_derived_scqa(
    entity_name: str | None,
    category_scores: list,
    recommendations: list,
) -> str | None:
    """DERIVED-tier SCQA (plan: 'DERIVE from report_analysis + scores' when
    no report_synthesis.md / DOCX exec-summary ships). Assembles a 4-part
    Situation/Complication/Question/Answer markdown purely from the entity's
    OWN extracted category scores + recommendations — deterministic, no
    fabrication. Returns None when there are no scores to anchor it."""
    # A real DMA maturity score clamps to [1.0, 5.0] (package_csvs:198), so a
    # 0.0 is a placeholder sentinel — never "zero maturity". Including it
    # rendered "**0.00** overall" on clients whose category_summary shipped
    # 0.0 placeholders even though real subcap scores existed (aafcu: 0.00
    # shown vs 2.36 real). Drop the placeholders: a mix averages only the
    # real scores, and an all-placeholder set returns None so the richer
    # deepen_narrative pass (grounded in real subcap_scores) fills it instead.
    scored = [
        c for c in category_scores
        if getattr(c, "score", None) is not None and c.score > 0
    ]
    if not scored:
        return None
    name = (entity_name or "The entity").strip()
    overall = sum(c.score for c in scored) / len(scored)

    def _label(c: object) -> str:
        nm = (getattr(c, "category_name", None)
              or getattr(c, "category_id", None) or "").strip()
        # Never emit a blank-name "(2.8)" placeholder when both the name and the
        # id are missing (2026-06-24: 74/94 SCQAs shipped "(2.8), (2.5)").
        return f"{nm} ({c.score:.1f})" if nm else f"a leading capability ({c.score:.1f})"

    strengths = sorted(scored, key=lambda c: c.score, reverse=True)[:3]
    # gaps: largest negative vs peer median, else lowest absolute.
    gaps = [c for c in scored if getattr(c, "peer_median", None) is not None
            and c.score - c.peer_median <= -0.3]
    gaps.sort(key=lambda c: c.score - (c.peer_median or 0))
    if not gaps:
        gaps = sorted(scored, key=lambda c: c.score)[:3]
    gaps = gaps[:3]
    rec_titles = [
        t for r in recommendations[:3]
        if (t := (getattr(r, "title", None) or "").strip()) and t != "(untitled)"
    ]

    parts = [
        f"## 1. Situation\n{name} scores **{overall:.2f}** overall across "
        f"{len(scored)} capability categories. Relative strengths: "
        f"{', '.join(_label(c) for c in strengths)}.",
        "## 2. Complication\n" + (
            "Largest gaps vs the peer cohort: "
            + ", ".join(
                f"{getattr(c, 'category_name', None) or c.category_id} "
                f"({c.score:.1f} vs peer {c.peer_median:.1f})"
                if getattr(c, "peer_median", None) is not None
                else _label(c)
                for c in gaps
            ) + "."
        ),
        "## 3. Question\nWhere should investment focus to close the maturity "
        f"gap — starting with {', '.join(getattr(c, 'category_name', None) or c.category_id for c in gaps)}?",
        "## 4. Answer\n" + (
            "Prioritised moves: " + "; ".join(rec_titles) + "."
            if rec_titles else
            "Prioritise the lowest-maturity categories above; detailed "
            "recommendations pending analyst synthesis."
        ),
        "\n*Derived from extracted scores + recommendations (no analyst "
        "synthesis shipped).*",
    ]
    return "\n\n".join(parts)


def find_report_synthesis(root: Path) -> Path | None:
    """Locate `report_synthesis.md` within the resolved package root.

    Checks the canonical dirs first, then RECURSIVELY (Tristate nests it in
    `08_appendices/analysis/`) so any layout is captured."""
    for sub in REPORT_SYNTHESIS_DIRS:
        for name in REPORT_SYNTHESIS_NAMES:
            p = root / sub / name
            if p.exists():
                return p
    for name in REPORT_SYNTHESIS_NAMES:
        hit = next(iter(sorted(root.glob(f"**/{name}"))), None)
        if hit is not None:
            return hit
    return None
