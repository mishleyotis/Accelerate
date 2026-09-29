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

WIDENED 28-09-2026 (QA audit F-L14-041). The shipped prose carried a band rule
the app does not have — "0.00–1.49 Activating, 1.50–2.49 Building, 2.50–3.49
Competing, 3.50–5.00 Differentiating" (the app cuts strictly at 2 / 3 / 4 on
the raw score), the retired fifth-band hex #185F60 on Differentiating, an
"M5 | Transformational" rubric row, "17 rollups" and "~72 capabilities" — and
this check passed with 0 findings because its M5/Transformational rules wanted
a band word on the same line. `Transformational` is now flagged wherever it
appears (a line that states the prohibition, or a lineage line, stays exempt);
the deck cut-offs, the retired hex and the two counts have rules of their own;
`deprecated/` directories are not scanned.
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
SKIP_PARTS = {"__pycache__", "engine", "deprecated"}   # the engine COMPUTES these counts; deprecated/ is not shipped prose


def _retired_scripts() -> frozenset:
    """The retired writers, read from their one owner (audit_skills.py): a
    retired script's legacy body names the JSON plane it used to write, and
    that is history behind a refusal, not a claim."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("audit_skills", HERE / "audit_skills.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return frozenset(mod.RETIRED_WRITERS)


RETIRED_SCRIPTS = _retired_scripts()

#: Lines mentioning the retired taxonomy on purpose. One of these words on
#: the line makes the literal a lineage statement rather than a claim about
#: the current catalogue.
P1C5_RANGE = re.compile(r"\bP1C1\s*[-–]\s*P1C5\b")
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
    r"nowhere|removed|banned|illegal|violation|do not exist|any occurrence",
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

#: Moody's as a SOURCE the run should call, rather than a line saying it is
#: not wired: the enrichment inventory and the agents that refuse it must
#: name it to refuse it.
MOODYS_CLAIM = re.compile(
    r"connector|enrichment|search|source|data|scorecard|protocol|dual", re.I)
NOT_WIRED = re.compile(r"not wired|unauthenticated|grants nothing|OAuth", re.I)

#: A batch-era stop, on a line about batches or checkpoints.
#: The deck skill's "wait for continue" is a person approving a slide-plan
#: batch, so the research tier's numbered batches and its checkpoint are the
#: context, not the word "batch" alone.
BATCH_CONTEXT = re.compile(r"Batch\s*[1-6]\b|BATCH\s*[1-6]\b|HANDOFF SUMMARY|[Cc]heckpoint")

#: LEGACY as a recency band, not the LEGACY_ANCHORED arc shape or a
#: "legacy system" in an estate.
RECENCY_CONTEXT = re.compile(r"CURRENT|RECENT|DATED|ARCHIVAL|recency|months?|mo\b", re.I)

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
    ("agents/checkers/exclusion-boundary-auditor.md",
     "`entity_ids`, `Transformational`"): "the excluded-vocabulary net names "
                                          "the token it excludes",
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
    ("skills/dma-surface-production/03-pages/rulebooks/heatmap/H4.md",
     "Shape notes, measured"): "the measured shape of a v5.0-pinned client",
    ("skills/dma-surface-production/scripts/check_payload.py",
     "MEM-0022"): "a recorded historical defect, not a current claim",
    ("skills/dma-assessment/references/capability_criteria.md",
     "Two scales"): "the paragraph that teaches the score/band distinction",
    ("skills/dma-research/references/diagnostic_questions.md",
     "which is the claim this"): "quotes the stale claim in order to retract it",
    ("skills/dma-research/scripts/merge_evidence.py",
     "baked into the signature"): "quotes the removed default to explain it",
    # ── the batch-era rules (29-09-2026) ──
    ("docs/HEADLESS-AUDIT-2026-09-03.md", ""): "a dated audit record of what "
                                              "the container held that day",
    ("docs/END-TO-END.md", "evidence_index.json` is classified"):
        "a recorded ingest behaviour (AUD-0091) for a legacy package's index file",
    ("skills/dma-research/references/CHANGELOG.md", ""): "version history, by name",
    ("skills/dma-surface-production/02-inputs/5-corpus-map.md",
     "748 of 752"): "a measured artefact of the reference package",
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
         "prose — the fifth SCORE level is 'Leading' (engine/rubric.py)", None),
        (re.compile(r"0\.00\s*[–-]\s*1\.49|1\.50\s*[–-]\s*2\.49|"
                    r"2\.50\s*[–-]\s*3\.49|3\.50\s*[–-]\s*5\.00"),
         "1.50 / 2.50 / 3.50 band cut-offs",
         "bands are strict less-than on the raw score: <2 Activating · "
         "<3 Building · <4 Competing · ≥4 Differentiating "
         "(apps/web/lib/bands.js ≡ engine.contract.band_of)", BAND_CONTEXT),
        (re.compile(r"185F60", re.I), "#185F60",
         "the retired fifth-band hex; Differentiating renders #139F94 and "
         "only apps/web/lib/bands.js maps a band to a colour", None),
        (re.compile(r"\b17\s+rollups\b", re.I), "17 rollups",
         f"one rollup per category: {c['categories']} in "
         f"{c['catalogue_version']}", None),
        (re.compile(r"~\s*72\s+capabilit", re.I), "~72 capabilities",
         f"the catalogue holds {c['capabilities']} capabilities", None),
        # ── the batch era's tokens (QA audit F-L11-042, 29-09-2026) ──
        (re.compile(r"\b06_handoff\b"), "06_handoff",
         "the run tree is engine.runstate.SUBDIRS; the handoff is the packet "
         "`engine.cli handoff` writes under 07_qa", None),
        (re.compile(r"/home/claude/"), "/home/claude/",
         "no container path in prose: the run root is <ROOT>/<RUN_ID>", None),
        (re.compile(r"Moody"), "Moody's",
         "declared, not wired (02-inputs/enrichment_sources.json); the "
         "connectors are Exa, Tavily, Clay and Explorium, and the tools rule "
         "is RESEARCH-PROTOCOL.md § Tools", MOODYS_CLAIM),
        (re.compile(r"\bP1C1\s*[-–]\s*P1C5\b"), "P1C1-P1C5",
         "P1C5 is the killed 17th category: the governance and strategy "
         "categories are P1C1–P1C4", None),
        (re.compile(r"safeguard_gates\.md"), "safeguard_gates.md",
         "retired: the 16 research-era gates; the SG family lives in "
         "apps/mcp/dma_mcp/gates.py alone", None),
        # the research plane's bare file; the assessment's checkpoint
        # `01_evidence_index.json` is that skill's own procedure to settle
        (re.compile(r"(?<!\w)evidence_index\.json"), "evidence_index.json",
         "no JSON plane beside the run; evidence enters through "
         "`engine.cli evidence` and lives in the workbook", None),
        # the research tier's batch stop — the deck skill's "wait for
        # continue" is a person approving a slide plan, which is the point
        (re.compile(r"[Ww]ait for ['\"“]?continue"), "wait for continue",
         "nothing waits for continue: the driver re-dispatches and a lane "
         "out of budget checkpoints and ends its turn", BATCH_CONTEXT),
        # the 18/36 ladder boundaries, not any 18-month span
        (re.compile(r"<\s*18\s*mo\b|\b18\s*[-–]\s*36\s*mo"), "18-month recency",
         "the recency ladder is contract.RECENCY_LADDER: CURRENT <12 · RECENT "
         "<24 · DATED <36 · STALE <48 · ARCHIVAL, UNVERIFIED undated", None),
        (re.compile(r"\bLEGACY\b"), "LEGACY (recency)",
         "the 36–48 month band is STALE (QA Report B-09; contract.RECENCY_LADDER)",
         RECENCY_CONTEXT),
        (re.compile(r"\bweb_fetch\b"), "web_fetch",
         "a page is read as windows through `engine.cli fetch`; a whole-page "
         "fetch is the largest lever on the bill (RESEARCH-PROTOCOL.md § Tools)", None),
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
            if p.suffix not in SCAN_EXT or SKIP_PARTS & set(p.parts) \
                    or p.name in RETIRED_SCRIPTS:
                continue
            for n, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                if LINEAGE.search(line) and not P1C5_RANGE.search(line):
                    continue
                rel = str(p.relative_to(root))
                if FORBIDDING.search(line) or NOT_WIRED.search(line) or _exempt(rel, line):
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
