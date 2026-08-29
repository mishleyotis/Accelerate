#!/usr/bin/env python3
"""What each report must contain, as data a renderer can enforce.

WHY THIS EXISTS.

  AUD-0105  every section of both v8 templates opens with a LENGTH band whose
      lower bound is "a blocking gate, so a section under its minimum is
      treated as incomplete" — and "no line of code anywhere measures a word
      count". The minimums are here, in a number a renderer compares against.
  AUD-0107  thirteen workbook sheets named as INPUTS by the two templates are
      absent from the workbook, "leaving §3.2 and §3.3 with no source at all".
      Every section below names the sheets it reads, and a section whose input
      is empty renders an explicit NO SOURCE block rather than nothing.
  AUD-0145  the archive's renderer enforced an insight-card floor of 3 where
      the template's blocking minimum is 8. One number, here.

PROVENANCE. The pinned v8 templates are Drive documents that no code path can
resolve (AUD-0069), so this spec is the repository's declaration of their
control blocks — section ids, headings, minimums and inputs — not a copy of
them. `--spec` on the renderer takes a JSON override, so when the real
template is exported, the divergence is a diff rather than a silent
substitution.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: The template's own blocking minimum for insight cards. AUD-0145.
INSIGHT_CARD_MIN = 8


@dataclass(frozen=True)
class Section:
    id: str
    heading: str
    min_words: int          # blocking: a section under this is incomplete
    inputs: tuple           # the workbook sheets this section reads
    requires_citation: bool = True
    kind: str = "section"
    note: str = ""


@dataclass(frozen=True)
class ReportSpec:
    key: str
    title: str
    filename: str           # {entity} {date} interpolated; the app classifies on it
    min_words: int
    sections: tuple
    extra: dict = field(default_factory=dict)

    def section(self, sid: str) -> Section | None:
        for s in self.sections:
            if s.id == sid:
                return s
        return None


CLIENT_RESEARCH = ReportSpec(
    key="client_research",
    title="Client Research Profile",
    # `client_profile` is the app's registry name for this artefact
    # (classification.py priority 3) and `.docx` is the only extension it
    # matches — AUD-0003 measured the produced `client_profile.md` returning
    # None from classify(), so the report was uningestable.
    filename="Client_Profile_Research_{entity}_{date}.docx",
    min_words=2500,
    sections=(
        Section("1", "Entity and scope", 150,
                ("Run_Metadata", "Handoff_Lock"), requires_citation=False),
        Section("2", "What we searched, and what we did not", 200,
                ("Search_Log", "Coverage"), requires_citation=False),
        Section("3", "Evidence base", 250, ("Evidence_Detail", "Coverage")),
        Section("4", "Capability picture by pillar", 600,
                ("P1_Subcap_Scoring", "P2_Subcap_Scoring",
                 "P3_Subcap_Scoring", "P4_Subcap_Scoring")),
        Section("5", "Insight cards", 400, ("Report_Narrative",),
                kind="insight_card",
                note=f"blocking minimum {INSIGHT_CARD_MIN} cards"),
        Section("6", "Technology and utilisation", 300,
                ("Evidence_Detail", "Report_Narrative")),
        Section("7", "Negative findings and what they bound", 250,
                ("P1_Subcap_Scoring", "Search_Log")),
        Section("8", "Where each artefact lives", 120,
                ("Run_Metadata", "Handoff_Lock"), requires_citation=False),
    ),
)

ASSESSMENT = ReportSpec(
    key="assessment",
    # `assessment_report` is the highest-ranked report name the classifier
    # knows (priority 2, rank 0).
    title="Digital Maturity Assessment Report",
    filename="DMA_Assessment_Report_{entity}_{date}.docx",
    min_words=3500,
    sections=(
        Section("1", "Executive summary", 350,
                ("Report_Narrative", "Coverage")),
        Section("2", "Method, scope and limits", 250,
                ("Run_Metadata", "Coverage", "Gate_Log"),
                requires_citation=False),
        Section("3", "Maturity by pillar", 700,
                ("P1_Subcap_Scoring", "P2_Subcap_Scoring",
                 "P3_Subcap_Scoring", "P4_Subcap_Scoring")),
        Section("4", "Evidence and its limits", 300,
                ("Evidence_Detail", "Coverage")),
        Section("5", "Findings", 500, ("Report_Narrative",), kind="finding"),
        Section("6", "Peer position", 250, ("Report_Narrative",)),
        Section("7", "Recommendations", 500, ("Report_Narrative",),
                kind="recommendation"),
        Section("8", "What would change this assessment", 200,
                ("Gate_Log", "Coverage"), requires_citation=False),
    ),
)

SPECS = {s.key: s for s in (CLIENT_RESEARCH, ASSESSMENT)}


def from_json(doc: dict) -> ReportSpec:
    """Build a spec from an exported template's control blocks."""
    return ReportSpec(
        key=doc["key"], title=doc["title"], filename=doc["filename"],
        min_words=int(doc["min_words"]),
        sections=tuple(Section(
            id=str(s["id"]), heading=s["heading"],
            min_words=int(s["min_words"]), inputs=tuple(s.get("inputs", ())),
            requires_citation=bool(s.get("requires_citation", True)),
            kind=s.get("kind", "section"), note=s.get("note", ""))
            for s in doc["sections"]),
        extra=doc.get("extra", {}),
    )
