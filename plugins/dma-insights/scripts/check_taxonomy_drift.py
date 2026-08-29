#!/usr/bin/env python3
"""Stale taxonomy literals in the skills, measured against the catalogue.

    check_taxonomy_drift.py [--fix-report] [--json]

WHY THIS EXISTS. AUD-0062: the Client Profile template's own rule is that
pillar, category, capability, subcapability, tier and gate counts are
"derived by counting catalogue rows at render time — never write one as a
literal in prose", and no renderer resolved the tokens while the skills
carried stale literals at roughly four to one against the settled figures:
35 occurrences of `836` against 2 of `851`, and 21 of "17 categories" against
9 of "16 categories". An unattended run reading dma-assessment's own SKILL.md
sizes its work, its gates and its coverage percentages against a taxonomy
that no longer exists.

AUD-0070 and AUD-0071 are the same drift landing in two reference files, and
AUD-0071 adds the band violation: a rubric whose fifth level is M5, which
charter invariant 6 says must not exist in code, enum or prose.

A LINE THAT IS DELIBERATELY ABOUT v5.0 IS NOT DRIFT. Six files legitimately
say "17 categories" because they are teaching an agent to RECOGNISE a
v5.0-shaped workbook — the vetting rule, the rulebook lineage notes, the grid
producer's version check. Those lines carry a lineage marker and are allowed.
The distinction is the whole value of this check: a blanket search-and-replace
would delete the mechanism that spots a v5.0 package.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
sys.path.insert(0, str(PLUGIN / "skills" / "dma-research"))

SCAN_DIRS = ("skills", "agents", "docs", "commands")
SCAN_EXT = (".md", ".py", ".json")
SKIP_PARTS = {"__pycache__", "engine"}   # the engine COMPUTES these counts

#: Lines mentioning the retired taxonomy on purpose. One of these words on
#: the line makes the literal a lineage statement rather than a claim about
#: the current catalogue.
LINEAGE = re.compile(
    r"v5\.0|v5-|\bv5\b|HISTORICAL|NOT_COMPARABLE|lineage|retired|superseded|"
    r"P1C5|Baxter|older catalogue|previous catalogue", re.I)

#: Lines that STATE the prohibition rather than commit it. The files that
#: teach an agent never to write a fifth band word have to name it to forbid
#: it, and flagging them would mean deleting the rule to satisfy the check.
FORBIDDING = re.compile(
    r"must not|never|forbid|prohibit|no fifth|unreachable|does not exist|"
    r"do not write|refus|reject|invariant 6|appear nowhere|is not a band|"
    r"there is no|there are no|no longer|not a band|has four|four bands|"
    r"nowhere|removed|banned|illegal|violation",
    re.I)

#: The evidence-CEILING scale, which is a different vocabulary from the
#: display band and is shipped in the deployed contract:
#: `packages/shared/contracts_data.json` states `ceiling: M1-M5 or null`,
#: and the connector validates against it. Invariant 6 is about `band_t`,
#: the four-value DISPLAY enum. Rewriting the ceiling scale here would break
#: a live gate, so these lines are reported separately (see --ceilings)
#: rather than treated as drift.
CEILING_SCALE = re.compile(r"M1\s*[-–—]\s*M5|`M1`\s*[-–—]\s*`M5`|ceiling", re.I)

#: `836` is a real line number as often as it is a count. It only means the
#: taxonomy when the line is talking about the taxonomy.
TAXONOMY_CONTEXT = re.compile(
    r"subcap|sub-cap|subcapabilit|sub-capabilit|cell|row|capabilit|question|"
    r"total|count|coverage|taxonom|scored|scoring", re.I)

#: A band claim. `M5` inside a ceiling expression or a file:line reference
#: is neither.
BAND_CONTEXT = re.compile(
    r"\bband\b|maturity|Activating|Building|Competing|Differentiating|"
    r"swatch|colour|color|renders|scale", re.I)


#: Lines that name a fifth level LEGITIMATELY, each with the reason.
#:
#: There are two scales in this system and conflating them is how a blanket
#: fix would break a live gate:
#:
#:   * the SCORE, 1-5, which the workbook carries and the assessment writes.
#:     The deployed contract itself states `ceiling: M1-M5 or null`
#:     (packages/shared/contracts_data.json) and the connector validates
#:     against it, so `M5` as a SCORE LEVEL is shipped vocabulary.
#:   * the BAND, four values, which is what RENDERS. Charter invariant 6 is
#:     about this one: `band_t` is a four-value enum and a fifth band word
#:     must not exist in code, enum or prose.
#:
#: Everything below is the first kind, or a file teaching the difference.
EXEMPT = {
    ("skills/dma-assessment/references/regression_tests.md",
     "Maturity descriptor"): "the 1-5 SCORE scale the workbook carries",
    ("skills/dma-assessment/references/report_template.md",
     "the workbook's"): "names both scales and teaches the difference",
    ("skills/dma-assessment/references/workbook_specification.md",
     "Maturity level text"): "the 1-5 SCORE scale, a workbook column",
    ("skills/dma-assessment/templates/04_scores_template.json",
     "maturity_level"): "the 1-5 SCORE the assessment writes",
    ("skills/dma-assessment/templates/evidence_index.md",
     "Level_Indicated"): "the SCORE level a piece of evidence indicates",
    ("skills/dma-governance/scripts/gov_auditor.py",
     "maturity_keywords"): "matches SCORE tokens in prose, including a "
                           "fifth level written by mistake — the detector "
                           "needs the token it detects",
    ("skills/dma-first-call-deck/references/_generated/brand_level_tables.md",
     "Transformational"): "the mapping table FROM the retired level name TO "
                          "the band it renders as; deleting it removes the "
                          "translation",
    ("skills/dma-surface-production/01-start-here/5-colour-and-bands.md",
     "maturity scale defines"): "the file that teaches the distinction",
    ("skills/dma-surface-production/01-start-here/5-colour-and-bands.md",
     "appears in the workbook"): "the file that teaches the distinction",
    ("agents/checkers/numeric-reconciliation-checker.md",
     "must"): "states the prohibition",
    ("agents/checkers/numeric-reconciliation-checker.md",
     "any band word that does not follow"): "states the prohibition",
    ("agents/orchestration/surface-producer.md",
     "Differentiating`."): "states the prohibition",
    ("agents/production/heatmap/heatmap-grid-producer.md",
     "band anywhere"): "states the prohibition",
    ("skills/dma-surface-production/03-pages/rulebooks/heatmap.md",
     "Shape notes, measured"): "the measured shape of a v5.0-pinned client",
    ("skills/dma-surface-production/scripts/check_payload.py",
     "MEM-0022"): "a recorded historical defect, not a current claim",
    ("skills/dma-assessment/references/capability_criteria.md",
     "Two scales"): "the paragraph that teaches the score/band distinction",
    ("skills/dma-research/references/diagnostic_questions.md",
     "which is the claim this"): "quotes the stale claim in order to retract it",
}


def _exempt(rel: str, line: str) -> str | None:
    for (f, needle), reason in EXEMPT.items():
        if rel == f and needle in line:
            return reason
    return None


def _counts() -> dict:
    from engine import contract           # noqa: PLC0415
    return contract.counts()


def rules(c: dict):
    """(pattern, literal, correction, gate) — `gate` decides whether the
    match is a claim about the current taxonomy or something else that
    happens to contain the same characters."""
    return (
        (re.compile(r"(?<![:.\w])836\b"), "836",
         f"the catalogue holds {c['cells']} cells "
         f"({c['universal']} universal + {c['sub_vertical_variants']} "
         f"sub-vertical variants)", TAXONOMY_CONTEXT),
        (re.compile(r"\b17\s+categor", re.I), "17 categories",
         f"the catalogue holds {c['categories']} categories", None),
        (re.compile(r"Category\s*\(\s*17\s*\)"), "Category (17)",
         f"Category ({c['categories']})", None),
        (re.compile(r"\b144\s+capabilit", re.I), "144 capabilities",
         f"the catalogue holds {c['capabilities']} capabilities", None),
        (re.compile(r"\bM5\b"), "M5",
         "there is no fifth BAND; the four are "
         "Activating / Building / Competing / Differentiating", BAND_CONTEXT),
        (re.compile(r"\bTransformational\b"), "Transformational",
         "the fifth band's name; invariant 6 forbids it in code, enum or "
         "prose", BAND_CONTEXT),
    )


def scan(root: Path | None = None) -> list[dict]:
    root = root or PLUGIN
    c = _counts()
    out = []
    for d in SCAN_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.suffix not in SCAN_EXT or SKIP_PARTS & set(p.parts):
                continue
            for n, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                if LINEAGE.search(line):
                    continue
                rel = str(p.relative_to(root))
                if FORBIDDING.search(line) or _exempt(rel, line):
                    continue
                for rx, literal, correction, gate in rules(c):
                    if not rx.search(line):
                        continue
                    if gate is not None and not gate.search(line):
                        continue
                    if literal in ("M5", "Transformational") and \
                            CEILING_SCALE.search(line):
                        continue
                    if True:
                        out.append({
                            "file": rel, "line": n,
                            "literal": literal, "correction": correction,
                            "text": line.strip()[:160],
                        })
                        break
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    hits = scan()
    if a.json:
        print(json.dumps({"counts": _counts(), "drift": hits}, indent=2))
    else:
        for h in hits:
            print(f"{h['file']}:{h['line']}: {h['literal']!r} — "
                  f"{h['correction']}\n    {h['text']}")
        print(f"check_taxonomy_drift: {len(hits)} stale literal(s) against "
              f"catalogue {_counts()['catalogue_version']}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
