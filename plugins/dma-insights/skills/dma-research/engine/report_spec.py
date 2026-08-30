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


#: Card sections are a LIST, not a passage. Their `min_words` is the floor
#: for the whole section — every card concatenated, which is what the
#: renderer assembles and what a reader meets — while `card_min_words` is
#: the floor for one card.
CARD_KINDS = ("insight_card", "finding", "recommendation")
CARD_MIN_WORDS = 60


@dataclass(frozen=True)
class Section:
    id: str
    heading: str
    min_words: int          # blocking: a section under this is incomplete
    inputs: tuple           # the workbook sheets this section reads
    requires_citation: bool = True
    kind: str = "section"
    note: str = ""
    #: The section's INTERNAL ANATOMY — the subheadings it must carry, in
    #: order. Until 2026-08-30 nothing anywhere said what a section
    #: CONTAINS: the generated agent tables printed the heading under a
    #: column headed "what it must argue", and the seven apparatus bullets
    #: below were byte-identical for all sixteen. The measurable
    #: consequence was in the artefact — the renderer emitted body
    #: paragraphs with no Heading2 of their own, so the app's
    #: Heading2-grained parser stored each section as one undifferentiated
    #: preamble row, and `embed.py` could scope none of it to a pillar.
    #:
    #: Written into Body as `## <block>` lines, in this order.
    #: `narrative.write` refuses a body missing one or carrying them out of
    #: order; `reports.render` promotes each to a real Heading2. The
    #: parenthesised pillar form in §3/§4 is deliberate: it is the token
    #: `embed._PILLAR_TOKEN` already looks for.
    blocks: tuple = ()
    #: The payload sections this report section feeds. The legacy app had
    #: an explicit section→surface table; the current build lost it, and
    #: what replaced it was prose in the page packs naming sections by
    #: description ("the per-pillar deep dives") — several of which name
    #: sections that no longer exist. This is that map, in the one place
    #: both the agents and the surface census can read it.
    surfaces: tuple = ()

    @property
    def card_min_words(self) -> int:
        return CARD_MIN_WORDS if self.kind in CARD_KINDS else 0


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
                ("Run_Metadata", "Handoff_Lock"), requires_citation=False,
                blocks=("Who this is",
                        "What was in scope",
                        "What was out of scope, and what that bounds"),
                surfaces=("overview.firmographics",)),
        Section("2", "What we searched, and what we did not", 200,
                ("Search_Log", "Coverage"), requires_citation=False,
                blocks=("How the search was built",
                        "What was searched",
                        "What was not searched, and what that bounds"),
                surfaces=("overview.evidence_coverage",)),
        Section("3", "Evidence base", 250, ("Evidence_Detail", "Coverage"),
                blocks=("What the register holds",
                        "Tier and recency profile",
                        "Concentration, and what a retraction would cost"),
                surfaces=("overview.evidence_coverage", "heatmap.evidence",
                          "heatmap.evidence_age")),
        Section("4", "Capability picture by pillar", 600,
                ("P1_Subcap_Scoring", "P2_Subcap_Scoring",
                 "P3_Subcap_Scoring", "P4_Subcap_Scoring"),
                blocks=("Strategy and governance (P1)",
                        "Customer experience (P2)",
                        "Operations (P3)",
                        "Data and technology (P4)"),
                surfaces=("heatmap.focus_areas", "heatmap.cell_evidence")),
        Section("5", "Insight cards", 400, ("Report_Narrative",),
                kind="insight_card",
                note=f"blocking minimum {INSIGHT_CARD_MIN} cards",
                blocks=("Claim", "Mechanism",
                        "What would change this"),
                surfaces=("insights.insights",)),
        Section("6", "Technology and utilisation", 300,
                ("Evidence_Detail", "Report_Narrative", "Tech_Register",
                 "Tech_Peer_Deployments"),
                blocks=("What is confirmed",
                        "What is inferred or only claimed",
                        "Where the estate does not yet reach"),
                surfaces=("techstack.techstack", "insights.landscape")),
        Section("7", "Negative findings and what they bound", 250,
                ("P1_Subcap_Scoring", "Search_Log"),
                blocks=("What was looked for and not found",
                        "The ladder behind each absence",
                        "What these absences cap"),
                surfaces=("heatmap.alerts", "overview.ceilings")),
        Section("8", "Where each artefact lives", 120,
                ("Run_Metadata", "Handoff_Lock"), requires_citation=False,
                blocks=("The artefacts", "How to re-run this"),
                surfaces=()),
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
                ("Report_Narrative", "Coverage"),
                # SCQA, because the overview page pack names `scqa_md` as
                # this section's shape and nothing was making it true.
                blocks=("Situation", "Complication", "Question", "Answer"),
                surfaces=("overview.exec_summary",)),
        Section("2", "Method, scope and limits", 250,
                ("Run_Metadata", "Coverage", "Gate_Log"),
                requires_citation=False,
                blocks=("How this was assessed",
                        "What was in scope",
                        "What the method cannot see"),
                surfaces=("heatmap.safeguard_gates",)),
        Section("3", "Maturity by pillar", 700,
                ("P1_Subcap_Scoring", "P2_Subcap_Scoring",
                 "P3_Subcap_Scoring", "P4_Subcap_Scoring"),
                blocks=("Strategy and governance (P1)",
                        "Customer experience (P2)",
                        "Operations (P3)",
                        "Data and technology (P4)"),
                surfaces=("heatmap.workbook_scores", "overview.scores")),
        Section("4", "Evidence and its limits", 300,
                ("Evidence_Detail", "Coverage"),
                blocks=("What the assessment rests on",
                        "Tier and recency profile",
                        "What the evidence cannot settle"),
                surfaces=("overview.evidence_coverage", "heatmap.evidence")),
        Section("5", "Findings", 500, ("Report_Narrative",), kind="finding",
                blocks=("Finding", "Consequence",
                        "What would change this"),
                surfaces=("overview.findings", "insights.insights")),
        Section("6", "Peer position", 250, ("Report_Narrative",
                                            "Peer_Benchmarks"),
                blocks=("The peer set, and how it was chosen",
                        "Where the client leads",
                        "Where the client trails"),
                surfaces=("overview.scores", "heatmap.workbook_scores")),
        Section("7", "Recommendations", 500, ("Report_Narrative",),
                kind="recommendation",
                blocks=("Recommendation", "Root cause", "Prerequisites",
                        "How we would know it worked"),
                surfaces=("platform.recommendations", "platform.roadmap",
                          "overview.opportunity")),
        Section("8", "What would change this assessment", 200,
                ("Gate_Log", "Coverage"), requires_citation=False,
                blocks=("What would move a score",
                        "What could not be verified",
                        "How to refresh this"),
                surfaces=("heatmap.evidence_age", "overview.ceilings")),
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
            kind=s.get("kind", "section"), note=s.get("note", ""),
            blocks=tuple(s.get("blocks", ())),
            surfaces=tuple(s.get("surfaces", ())))
            for s in doc["sections"]),
        extra=doc.get("extra", {}),
    )


if __name__ == "__main__":  # a library, but it must answer --help
    import argparse as _ap
    _ap.ArgumentParser(
        prog=__file__.rsplit("/", 1)[-1],
        description=__doc__.split("\n")[0],
        epilog="A library module: import it, or run the modules that do have "
               "a command line (cli, orient, floors_gate, validator, handoff, "
               "reports, strip_working_area, patch_validator, watchdog).",
    ).parse_args()
