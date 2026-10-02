#!/usr/bin/env python3
"""What each report must contain — READ FROM THE PINNED TEMPLATES, never typed here.

WHY THIS FILE CHANGED (owner, 2026-09-03: "the reports do not follow the
required format. Can these templates be retrieved from the repo?").

Until now this module DECLARED the two reports' sections itself — eight per
report, with headings such as "Entity and scope" and "What would change this
assessment" — because AUD-0069 recorded that the pinned templates were Drive
documents no code path could resolve. They can be, and they were: the Client
Profile Research Report is eight sections (1 Firmographics … 8 Workbook
References) and the Digital Maturity Assessment Report is eleven (1 Executive
Summary … 11 Workbook Traceability), each opening with a control block that
names its LENGTH band, INPUTS, FEEDS, MINIMUM DATA, MUST INCLUDE, MUST NOT and
FAIL IF. None of that matched what this file said, so every report the engine
ever rendered followed a format nobody had asked for, and the gold-standard
gate could only check section numbers against a docx the caller happened to
have.

So the spec is DATA: `references/templates/report_templates.json`, pinned from
the two owner Docs (markdown exports beside it), with the countable half of
each control block as `checks` and `forbid` regexes. This module loads it and
exposes the same `Section` / `ReportSpec` objects the writer, the renderer, the
gold gate and the agent generator already consume. A section added to the
JSON grows a writer table, a renderer heading, a gate row and an agent
paragraph at once; a heading changed in the Doc and re-pinned fails
`engine.template report-drift` until this file's data is reconciled.

  AUD-0105  every section's lower LENGTH bound is a blocking gate — `words_min`.
  AUD-0107  every section names the sheets it reads — `inputs`, mapped to the
            engine's own sheet names.
  AUD-0145  the insight-card floor is the template's 8, kept as INSIGHT_CARD_MIN
            and enforced as §5's `IC-NNN` check on the research profile.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

#: The template's own blocking minimum for insight cards (Client Profile §5.1).
INSIGHT_CARD_MIN = 8

#: Card sections are a LIST, not a passage: one row per card, each with its
#: own id. `pillar` is the assessment's §5 (exactly one card per pillar);
#: `recommendation` its §8 (five to eight REC-NN cards). `finding` and
#: `insight_card` are retained as vocabulary the workbook's `Kind` column has
#: carried, so an older row still reads.
CARD_KINDS = ("pillar", "recommendation", "finding", "insight_card")
#: Default per-card floor where the template states none.
CARD_MIN_WORDS = 60

_HERE = Path(__file__).resolve().parent
#: Inside the plugin: skills/dma-research/engine -> plugins/dma-insights.
TEMPLATES_DIR = _HERE.parents[2] / "references" / "templates"
TEMPLATES_JSON = TEMPLATES_DIR / "report_templates.json"


class TemplateUnavailable(RuntimeError):
    """The pinned template spec is not where the plugin ships it."""


@dataclass(frozen=True)
class Check:
    """One countable MINIMUM DATA rule: `pattern` must match at least `min`
    times (distinct matches when `distinct`), at most `max` when given;
    `per_card` applies it to each card of a list section."""
    pattern: str
    min: int = 1
    max: int | None = None
    distinct: bool = False
    label: str = ""
    per_card: bool = False

    def count(self, text: str) -> int:
        hits = re.findall(self.pattern, text or "")
        hits = [h if isinstance(h, str) else h[0] for h in hits]
        return len(set(hits)) if self.distinct else len(hits)


@dataclass(frozen=True)
class Forbid:
    """One countable MUST NOT rule: a match refuses the section."""
    pattern: str
    label: str = ""


@dataclass(frozen=True)
class Section:
    id: str
    heading: str
    min_words: int          # blocking: a section under this is incomplete
    inputs: tuple           # the workbook sheets this section reads
    requires_citation: bool = True
    kind: str = "section"
    note: str = ""
    #: The section's anatomy — the Doc's numbered subsections, in order.
    #: Written into Body as `## <block>` lines; `narrative.write` refuses a
    #: body missing one or carrying them out of order; `reports.render`
    #: promotes each to a real heading, which is the grain the app parses.
    blocks: tuple = ()
    #: The payload sections this report section feeds (the Doc's own Surface
    #: Alignment table, in payload-path vocabulary).
    surfaces: tuple = ()
    max_words: int | None = None          # advisory upper LENGTH bound
    purpose: str = ""
    minimum_data: str = ""
    must_include: str = ""
    must_not: str = ""
    fail_if: str = ""
    checks: tuple = ()
    forbid: tuple = ()
    card_prefix: str | None = None
    cards_min: int | None = None
    cards_max: int | None = None
    card_words_min: int | None = None
    card_words_max: int | None = None
    card_heading: str | None = None

    @property
    def is_card(self) -> bool:
        return self.kind in CARD_KINDS

    @property
    def card_min_words(self) -> int:
        if not self.is_card:
            return 0
        return int(self.card_words_min or CARD_MIN_WORDS)

    @property
    def card_floor(self) -> int:
        """How many cards the section needs before it is complete."""
        if not self.is_card:
            return 0
        if self.cards_min:
            return int(self.cards_min)
        return INSIGHT_CARD_MIN if self.kind == "insight_card" else 1


@dataclass(frozen=True)
class ReportSpec:
    key: str
    title: str
    filename: str           # {entity} {date} interpolated; the app classifies on it
    min_words: int
    sections: tuple
    extra: dict = field(default_factory=dict)
    short_title: str = ""
    drive_doc_id: str = ""
    markdown: str = ""
    front_matter: tuple = ()

    def section(self, sid: str) -> Section | None:
        for s in self.sections:
            if s.id == str(sid):
                return s
        return None


def _section_from(doc: dict) -> Section:
    return Section(
        id=str(doc["id"]), heading=doc["heading"],
        min_words=int(doc.get("words_min", doc.get("min_words", 0))),
        inputs=tuple(doc.get("inputs", ())),
        requires_citation=bool(doc.get("requires_citation", True)),
        kind=doc.get("kind", "section"), note=doc.get("note", ""),
        blocks=tuple(doc.get("blocks", ())),
        surfaces=tuple(doc.get("feeds", doc.get("surfaces", ()))),
        max_words=doc.get("words_max"),
        purpose=doc.get("purpose", ""), minimum_data=doc.get("minimum_data", ""),
        must_include=doc.get("must_include", ""), must_not=doc.get("must_not", ""),
        fail_if=doc.get("fail_if", ""),
        checks=tuple(Check(**c) for c in doc.get("checks", ())),
        forbid=tuple(Forbid(**f) for f in doc.get("forbid", ())),
        card_prefix=doc.get("card_prefix"), cards_min=doc.get("cards_min"),
        cards_max=doc.get("cards_max"), card_words_min=doc.get("card_words_min"),
        card_words_max=doc.get("card_words_max"), card_heading=doc.get("card_heading"),
    )


def from_json(doc: dict) -> ReportSpec:
    """Build a spec from one report's pinned control blocks."""
    sections = tuple(_section_from(s) for s in doc["sections"])
    return ReportSpec(
        key=doc["key"], title=doc["title"], filename=doc["filename"],
        min_words=int(doc.get("min_words") or sum(s.min_words for s in sections)),
        sections=sections, extra=doc.get("extra", {}),
        short_title=doc.get("short_title", ""),
        drive_doc_id=doc.get("drive_doc_id", ""),
        markdown=doc.get("markdown", ""),
        front_matter=tuple(doc.get("front_matter", ())),
    )


def load(path: Path | None = None) -> dict[str, ReportSpec]:
    p = Path(path) if path else TEMPLATES_JSON
    if not p.is_file():
        raise TemplateUnavailable(
            f"the pinned report templates are not at {p}. The plugin ships "
            f"them under references/templates/; a checkout without them "
            f"cannot say what a report must contain, and guessing is the "
            f"defect this file exists to end.")
    raw = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for key, doc in raw["reports"].items():
        spec = from_json(doc)
        if spec.key != key:
            raise TemplateUnavailable(
                f"report_templates.json keys {key!r} but the spec inside "
                f"says {spec.key!r}")
        out[key] = spec
    return out


SPECS: dict[str, ReportSpec] = load()
CLIENT_RESEARCH = SPECS["client_research"]
ASSESSMENT = SPECS["assessment"]

#: The template's own pinned metadata, for the gates and the drift check.
PINNED = json.loads(TEMPLATES_JSON.read_text(encoding="utf-8"))


def numbered_headings(key: str) -> list[str]:
    """`N. Heading` for every section, the form the rendered Heading1 takes."""
    return [f"{s.id}. {s.heading}" for s in SPECS[key].sections]


if __name__ == "__main__":  # a library, but it must answer --help
    import argparse as _ap
    ap = _ap.ArgumentParser(
        prog=__file__.rsplit("/", 1)[-1],
        description=__doc__.split("\n")[0],
        epilog="A library module: import it, or run `engine.narrative contract` "
               "to print every section's blocks, inputs and feeds.")
    ap.parse_args()
    for k, spec in SPECS.items():
        print(f"{k}: {spec.title} — {len(spec.sections)} sections, "
              f"{spec.min_words}+ words (pinned from Doc {spec.drive_doc_id})")
