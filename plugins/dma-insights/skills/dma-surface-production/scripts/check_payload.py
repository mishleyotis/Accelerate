#!/usr/bin/env python3
"""Local pre-submit checks for a DMA Insights page payload.

Catches the cheap failures here so submissions spend their round trips on the
expensive ones — grain, identity and grounding — which only the server can check.

    python scripts/check_payload.py payload.json --page overview
    python scripts/check_payload.py payload.json --page heatmap --strict
    python scripts/check_payload.py payload.json --page heatmap \
        --subvertical SV2 --cells bundle.json

What it covers beyond the contract: face budgets (CG-12), item dating (CG-10),
sentence case (CG-11), closed vocabularies on TEXT columns (CG-09), per-ITEM
citation (AG-03), and the P2 recommendation card's anatomy — the two lists both
called prerequisites, the KPI that is not a KPI without its baseline, and
`provenance`, which the contract calls required and which shipped absent on
every recommendation of the run this was written against.

The governing rule is `check_agreement.py`'s: **LOCAL ⊆ SERVER on the classes
both police**. A local BLOCK the connector does not raise is a false alarm, and
it costs a producer a repair cycle on content that would have passed. Measured
against a run whose six pages all PASS the gates, four rules here were charging
exactly that, and all four are fixed in place rather than deleted:

  · AG-03 now implements the exemption its own registry text states — a
    recorded absence carrying its ladder asserts nothing (629 false blocks).
  · the raw-taxonomy-code rule no longer fires on fields that exist to carry
    ids: `subcap_id`, `catalogue_path`, `linked_subcap_ids` (94 false blocks).
  · CG-09 on `arc_shape` follows the server's `leading` rule — the badge leads,
    the sentence of evidence follows it.
  · the prose rules ask the KEY, not the whole JSON path, so `context.*`,
    `exec_summary.*` and `platform_story.*` no longer read as prose wholesale.

Each of the four keeps its teeth: a bare empty citation list with no ladder
still blocks, a taxonomy code inside real prose still blocks, a coined
`arc_shape` still blocks, and a genuinely clipped paragraph still warns.

Two flags unlock the two checks that need to know something about the run:
`--subvertical` (the entity's, SV1-SV9 or the workbook code) turns on the
sub-vertical scope check, and `--cells` (a bundle JSON, or a bare list of
cell ids) turns on cell-linkage resolution. Without them those two say so
rather than passing silently.

Exit code 0 = clean, 1 = blocking problems found.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

# ── the section registry, by page ────────────────────────────────────
SECTIONS = {
    "overview": ["scores", "firmographics", "why_now", "exec_summary", "opportunity",
                 "findings", "leadership", "financial_series", "sentiment", "ceilings",
                 "evidence_coverage", "thought_leadership"],
    "insights": ["insights", "landscape"],
    "heatmap": ["workbook_scores", "focus_areas", "cell_evidence", "evidence",
                "value_chain", "alerts", "safeguard_gates", "evidence_age",
                "cohort_patterns"],
    "platform": ["platform_story", "recommendations", "starters", "roadmap", "stairstep"],
    "context": ["timeline", "issue_register", "regulatory_standing", "context_sentiment",
                "acquisitions"],
    "techstack": ["techstack"],
}
OPTIONAL = {"heatmap": {"value_chain", "cohort_patterns"}}

# Sections whose content is client-visible and therefore must declare redaction.
NEEDS_INTERNAL_ONLY = {
    "scores", "firmographics", "findings", "exec_summary", "opportunity", "ceilings",
    "evidence_coverage", "sentiment", "thought_leadership", "insights",
    "cell_evidence", "safeguard_gates", "cohort_patterns", "platform_story",
    "recommendations", "starters",
}

# ── vocabularies ─────────────────────────────────────────────────────
EID = re.compile(r"\b(?:E|EV|INT)-[A-Z0-9]+(?:-[A-Z0-9]+){0,3}(?![A-Za-z0-9-])")
# Base cells (P4C3.1.2) AND sub-vertical variant cells (P1C1.3.CU1,
# P3C3.4.RIA1, P2C3.2.IC1) — a 2-4 letter vertical tag plus an index as the
# terminal segment. The old expression could not match a variant cell at
# all, so this checker refused 32 of one run's legitimately served RIA/WM
# cells as malformed while the connector's own _SUBCAP_RE accepted every
# one (MEM-0032, MEM-0026). The connector's gate is the authority; a local
# checker stricter than the gate is a false alarm, not a higher standard.
SUBCAP = re.compile(
    r"^P[1-4]C\d{1,2}(?:\.\d{1,2}){0,2}(?:\.[A-Z]{2,4}\d{1,2})?[a-z]?$")
AGENT_IDS = {"ic_id": r"^IC-\d{1,3}$", "f_id": r"^F-\d{1,2}$", "fa_id": r"^FA-\d{1,2}$",
             "ts_id": r"^TS-\d{1,3}$", "wn_id": r"^WN-\d{1,2}$"}
TIERS = {"T1", "T2", "T3", "T4", "T5"}
RECENCY = {"CURRENT", "RECENT", "DATED", "STALE", "ARCHIVAL", "UNVERIFIED"}
CLAIMS = {"FACT", "INFERENCE", "HYPOTHESIS", "CEILING_ESTIMATE"}
STACK_LAYERS = {"OPS", "CUST", "DATA", "INFRA"}
STACK_STATUS = {"CONFIRMED", "INFERRED", "CLAIMED", "ABSENT"}
GATE_RESULT = {"PASS", "FAIL", "NOT_RUN"}
PEER_BASIS = {"table", "recomputed", "inferred", "cannot_estimate"}

BANNED_REGISTER = [
    (r"\bleverage\b", "consultant register"),
    (r"\bbest.in.class\b", "consultant register"),
    (r"\bjourney\b", "consultant register"),
    (r"\blacks\b", "deficit framing"),
    (r"\bfails to\b", "deficit framing"),
    (r"\bworld.class\b", "consultant register"),
    (r"^#{1,6}\s", "markdown heading in a text field"),
    (r"\*\*", "markdown emphasis in a text field"),
]
SENTINELS = [r"\bNaN\b", r"\bnan\b", r"\bnull\b(?!able)", r"\bundefined\b", r"\bN/A\b",
             r"\b-999\b", r"\bTBD\b", r"\bTODO\b"]

# ── the gates these local checks stand in for ────────────────────────
# Each block below names the gate the connector will emit if you skip it,
# so a local BLOCK and a server verdict read as the same sentence.

# CG-10 · the field that DATES an item on a surface. A second date on the
# same item (resolved_on on an ACTIVE matter, closed_on on an ANNOUNCED
# merger, appointed_on with no start date in the source) is legitimately
# null — the event has not happened — and is not listed here.
ITEM_DATING = {
    "timeline": ("events", "event_date", "the timeline places the event on an axis"),
    "issue_register": ("issues", "opened_on", "the register orders on opened_on "
                                              "and the Gantt draws from it"),
    "why_now": ("signals", "dated_on", "a why-now is an EVENT; an undated "
                                       "signal is dropped, not rendered"),
    "thought_leadership": ("entries", "published_on", "the card prints the date "
                                                      "beside the quote"),
    "firmographics": ("fields", "as_of", "the recency dot is computed from as_of"),
    "leadership": ("roster", "as_of", "a name with no verification date does "
                                      "not render"),
    "evidence_age": ("rows", "published_or_asof", "age_months and band are "
                                                  "computed from this date"),
}
ABSENCE_RUNGS = {"UNVERIFIED", "UNWORKED", "WORKED_ABSENT", "NOT_RUN", "undated",
                 "verified_absent", "verified_sparse", "cannot_estimate",
                 "empty_state"}
RUNG_KEYS = ("recency_band", "recency_tag", "band", "date_basis",
             "dating_basis", "undated_reason", "date_absence")

# CG-11 · a prose field on a client surface begins with a capital. Policed
# when the KEY is a prose key or the value ENDS as a sentence; never on an
# id, a hostname, a URL, an enum or a verbatim excerpt.
PROSE_KEYS = {
    "body", "rationale", "story", "story_md", "text", "framing", "synthesis",
    "summary", "narrative", "narrative_thread", "consequence",
    "consequence_of_waiting", "cost_of_acting_now", "why_this_sequence",
    "trigger", "window", "detection_basis", "dma_impact", "so_what", "what",
    "why", "reason", "not_run_reason", "note", "grain_note", "currency_note",
    "reach_note", "detail", "statement", "pattern_statement", "headline",
    "relevance_note", "effect_note", "mix_implication", "strategic_alignment",
    "plain_label", "rejected_alternative", "implication", "clause",
    "limiting_absence", "description", "justification", "closure_condition",
    "quarantine_reason", "sequencing_basis", "sequencing_reason",
    "denominator_definition", "target_basis", "enrichment_basis",
    "proxy_disclosure", "maturity_effect", "empty_reason",
}

# Keys that are never a sentence, in three families — because the rule that
# walked every string leaf read all three as prose:
#   · verbatim spans, locators and proper names (quoted, not written)
#   · the section envelope and the argument record (metadata ABOUT a section,
#     not content OF it)
#   · ids, enums and dates, each of which has its own check above
# Measured on a run whose six pages all PASS the connector's gates: every one
# of overview's 38 warnings was one of these read as prose.
NEVER_SENTENCE = {
    # verbatim spans, locators, proper names
    "excerpt", "quote", "verbatim", "snippet", "url", "source_url",
    "linkedin_url", "source_domain", "domain", "email", "phone",
    "source_name", "source_title", "vendor", "product", "name", "field",
    # the section envelope and the r_layer argument record
    "produced_at", "producer_version", "internal_only", "e_id", "e_ids",
    "claim_label", "confidence", "verdict", "challenger", "outcome",
    # ids, enums, dates
    "id", "subcap_id", "catalogue_path", "unit", "value", "kind", "layer",
    "status", "tier", "signal", "phase", "provenance", "result", "severity",
    "recency", "recency_band", "recency_tag", "band", "as_of", "event_date",
}
CAMEL_FIRST_WORD = re.compile(r"^[a-z]+[A-Z]")     # nCino, iOS, eBay

# Keys whose value is a LABEL — a card-face claim carrying a word budget, not
# a paragraph. The contract states the budgets (findings `title` <=12 words,
# `consequence` 6-14 words, landscape `detail` one line), and a label takes no
# terminal stop.
LABEL_KEYS = {"title", "headline", "statement", "consequence", "label",
              "metric", "l4_feature", "theme"}
# Long enough to BE a paragraph. Under it, a prose key is holding a card-face
# label and a missing full stop is the house style, not a clip; over it, a
# missing stop is the clipped text this rule exists to catch.
PROSE_MIN_WORDS = 15

# A key holds prose when the KEY says so. Asking the question of the whole
# JSON PATH — which is what this checker did — made every leaf on the
# `context` page match "text", every leaf under `exec_summary` match
# "summary", and every leaf under `platform_story` match "story". On a run
# whose six pages all pass the server's gates that collision produced 94
# blocking "raw taxonomy code" findings on fields that exist to carry ids,
# and terminal-punctuation warnings on `e_ids`, `internal_only`,
# `produced_at`, `producer_version`, `claim_label` and the whole `r_layer`.
PROSE_KEY_HINTS = ("body", "rationale", "story", "text", "framing",
                   "synthesis", "summary", "title", "headline", "statement",
                   "narrative", "consequence")

# Fields that EXIST to carry a taxonomy id. The humanise rule is about PROSE:
# a cell id in `subcap_id`, `catalogue_path` or `linked_subcap_ids` is the
# field doing its job, and refusing it costs a repair cycle on content the
# gates accept.
ID_BEARING_KEYS = {"subcap_id", "catalogue_path", "cell", "cell_id", "anchor"}


def is_prose_key(key: str) -> bool:
    """Does this key hold prose a client reads?

    Deliberately the SAME hint list the rule always used, asked of the key
    rather than the path. Widening it to every key in PROSE_KEYS was tried and
    reverted: it raised 26 fresh blocks on a page the connector passes, which
    is the cost this repair exists to remove, not a standard to add.
    """
    if key in NEVER_SENTENCE:
        return False
    return any(h in key for h in PROSE_KEY_HINTS)


def carries_ids(key: str) -> bool:
    """Does this key exist to carry identifiers rather than sentences?

    Held INDEPENDENTLY of is_prose_key on purpose. Today's hint list happens
    not to reach `subcap_id` or `catalogue_path`, so the two guards agree — but
    the 94 false blocks came from a prose test that WAS wide enough to reach
    them, and the next widening would bring them straight back. A field that
    exists to carry a taxonomy code is exempt from the humanise rule as a
    standing property of the field, not as a side effect of how prose is
    currently recognised.
    """
    return (key in ID_BEARING_KEYS
            or key.endswith(("_id", "_ids", "_path", "_code", "_codes")))


def leaf_key(path: str) -> str:
    """The final key of a walked path, with any list index stripped."""
    return path.rsplit(".", 1)[-1].split("[")[0]

# CG-12 · what renders in a chip, badge or single-line slot, and what the
# long form is instead. path is section-relative; `[*]` walks a list.
FACE_BUDGETS = {
    "why_now": [
        ("signals[*].window", {"min_words": 20, "max_words": 40},
         "the drilldown's Window row",
         "the closing EVENT and its date; the argument belongs in "
         "consequence_of_waiting"),
        ("signals[*].trigger", {"min_words": 25, "max_words": 45},
         "the card face, cut at its first clause",
         "what changed, dated and cited"),
    ],
    "techstack": [
        ("items[*].detection_basis", {"max_chars": 160, "max_sentences": 1},
         "the register row and the T3 detail header",
         "ONE CLAUSE saying how the product was placed in this estate; what "
         "it bears on belongs in dma_impact (40-90 words)"),
    ],
    "landscape": [("tiles[*].detail", {"max_chars": 90},
                   "the landscape tile's one-line detail",
                   "the count's meaning in one line")],
    "safeguard_gates": [("gates[*].plain_label", {"min_words": 6, "max_words": 24},
                         "the client-visible gate card",
                         "a human sentence of 8-18 words")],
    "opportunity": [("tiles[*].addressable_cells[*].feature_that_addresses_it",
                     {"max_chars": 80}, "the addressable-cell chip",
                     "the feature's name, not its case")],
    # P2 · the recommendation card. See 04-craft/4-card-anatomy.md — the face
    # is a half-width column that halves again at tablet width, so the title
    # sits on one flex line beside two badges, the L4 feature is a catalogue
    # feature NAME rather than a solution sentence, and the KPI metric shares
    # a footer row with the readiness gate and the cell count.
    "recommendations": [
        ("recommendations[*].title", {"min_words": 4, "max_words": 9},
         "the card header, on one line beside the phase and effort badges",
         "the initiative in a phrase; the argument is root_cause"),
        ("recommendations[*].l4_feature", {"max_words": 6},
         "the card's sub-header and a badge in the modal head",
         "the catalogue L4 FEATURE name ('Data Cloud', 'Workflow Engine'), "
         "not a description of the solution"),
        ("recommendations[*].kpi_triple.metric", {"max_words": 8},
         "the KPI footer cell, above baseline and target",
         "what gets counted; the numbers are baseline and target"),
        ("recommendations[*].phase", {"max_words": 1},
         "the phase badge, which the app prints as 'Phase <value>'",
         "the ordinal alone — '1', never 'Phase 1 (0-6 mo)'"),
    ],
}

# AG-03 · the item lists whose schema declares an evidence key. Derived from
# the live page contracts with the connector's own `_declared_ev_keys`, so
# this mirrors what the server will demand rather than guessing at it. Any
# OTHER list of objects is checked by the self-calibrating rule below.
ITEM_CITATIONS = {
    "focus_areas": ("focus_areas", "new_evidence_ids"),
    "cell_evidence": ("cells", "e_ids"),
    "evidence": ("evidence", "e_id"),
    "alerts": ("alerts", "new_evidence_ids"),
    "safeguard_gates": ("caps", "e_ids"),
    "evidence_age": ("rows", "e_id"),
    "firmographics": ("fields", "source_e_id"),
    "why_now": ("signals", "e_ids"),
    "findings": ("findings", "e_ids"),
    "leadership": ("roster", "source_e_id"),
    "financial_series": ("series", "source_e_id"),
    "sentiment": ("bars", "e_id"),
    "ceilings": ("rows", "e_ids"),
    "thought_leadership": ("entries", "e_id"),
    "insights": ("cards", "supporting_e_ids"),
    "recommendations": ("recommendations", "evidence_ids"),
    "starters": ("starters", "e_ids"),
    "stairstep": ("ladder", "e_ids"),
    "timeline": ("events", "e_ids"),
    "context_sentiment": ("context_tiles", "e_ids"),
    "acquisitions": ("rows", "e_ids"),
    "techstack": ("items", "e_ids"),
}
EV_KEYS = ("e_ids", "supporting_e_ids", "evidence_ids", "new_evidence_ids",
           "source_e_id", "e_id")
# An item that asserts nothing owes no citation, and there are exactly two
# honest shapes for that: a null-valued row, and a recorded absence carrying
# the ladder that established it. Same vocabulary the connector reads.
ABSENT_STATES = {"UNWORKED", "WORKED_ABSENT", "NOT_RUN", "verified_absent",
                 "verified_sparse", "cannot_estimate", "insufficient_cohort",
                 "empty_state", "quarantined", "ABSENT"}

# CG-09 · fields whose promoted column is plain TEXT but whose CONTRACT names
# a closed vocabulary. Add one only where the contract states the values —
# this is not a place to invent vocabulary.
CONTRACT_VOCABULARIES = {
    "timeline": {
        "events[*].signal": ("POSITIVE", "NEUTRAL", "NEGATIVE"),
        "events[*].kind": ("PLATFORM", "LEADERSHIP", "M&A", "REGULATORY",
                           "CHANNEL", "DATA", "SECURITY", "STRATEGY"),
    },
    "techstack": {
        "items[*].status": ("CONFIRMED", "INFERRED", "CLAIMED", "ABSENT"),
        "items[*].layer": ("OPS", "CUST", "DATA", "INFRA"),
    },
    "recommendations": {
        "recommendations[*].provenance": ("ANALYST", "DERIVED"),
        "recommendations[*].effort_band": ("S", "M", "L"),
    },
    "starters": {"starters[*].provenance": ("TEMPLATE_FILL", "ANALYST")},
    "thought_leadership": {
        "entries[*].kind": ("LINKEDIN POST", "CONFERENCE", "ARTICLE", "PODCAST",
                            "EARNINGS CALL", "BLOG", "PANEL"),
    },
}
# Fields whose contract says "one of these values WITH a clause of reasoning".
# The value has to LEAD, because that prefix is what a filter reads and what a
# badge prints; the clause after it is the contract doing its job, not a
# vocabulary breach. `maturity_effect` is the one that renders as
# "ADVANCED — the engagement stack was assembled component by component".
#
# `arc_shape` is here and not above because the SERVER marks it
# `"leading": True` (apps/mcp/dma_mcp/validation.py, `_CONTRACT_VOCABULARIES`
# under `context.timeline`): "the contract states the five 'with one sentence
# of evidence' — the badge must be one of them, what follows it is the
# producer's own prose". Values copied from that entry so the two lists cannot
# drift. Demanding an exact match here refused
# 'STEADY_INVESTMENT — <one sentence of evidence>' on a run the gates passed.
LEADING_VOCABULARIES = {
    "timeline": {
        "arc_shape": ("STEADY_INVESTMENT", "STOP_START", "POST_EVENT_CATCHUP",
                      "LEGACY_ANCHORED", "RECENT_ACCELERATION"),
        "events[*].maturity_effect": ("ADVANCED", "CONSTRAINED", "NEUTRAL"),
    },
    "thought_leadership": {"entries[*].alignment":
                           ("CORROBORATES", "CONTRADICTS", "EXTENDS")},
}
# The badge is the LEADING run of capitals and nothing else — the same
# expression the connector applies (`_LEADING_TOKEN` in validation.py). A
# `startswith` test would accept a coined word that merely opens with a
# vocabulary value; this refuses it, exactly as the server does.
LEADING_TOKEN = re.compile(r"^[A-Z][A-Z_]*")
# Fields the contract marks required-and-never-blank on an ITEM, which a
# missing-key check would otherwise pass silently because the key is simply
# absent rather than empty.
#
# `provenance` is a WARN and not a BLOCK on purpose, and the reason is a
# conflict this checker does not get to resolve. The Surface Specification
# states it per recommendation ("required, never blank; 32 clients shipped
# derived rows presented as analyst recommendations"). The Backend Schema
# stores one `provenance_t` per row from the ENVELOPE, and the writer spec
# fills that column from `sys:provenance` — the SUBMISSION-level argument to
# submit_page_payload, whose values are `analyst · derived · producer` and
# whose default is `producer`. So a per-item provenance validates and is then
# dropped. Send it (the contract asks for it) AND set the submission argument,
# and read `04-craft/4-card-anatomy.md` for the open question.
REQUIRED_ITEM_FIELDS = {
    "recommendations": [
        ("recommendations", "provenance", "WARN",
         "the contract states it per recommendation, ANALYST or DERIVED, "
         "never blank — 32 clients shipped derived rows presented as analyst "
         "judgement. Note that what PERSISTS is the submission-level "
         "provenance argument (analyst|derived|producer, default 'producer'), "
         "so set that too or every row serves as 'producer'"),
        ("recommendations", "cost_of_inaction", "BLOCK",
         "what degrades if this does not happen, over what horizon; where "
         "nothing grounds it, the contract's literal string is "
         "'no dated trigger established'"),
        ("recommendations", "root_cause", "BLOCK",
         "30-60 words, cited, saying why the gap exists — the card face "
         "line-clamps it to three lines and the modal opens on it"),
    ],
    "starters": [("starters", "provenance", "WARN",
                  "the contract states TEMPLATE_FILL or ANALYST per starter "
                  "and the card renders it; the stored column is the "
                  "submission-level provenance class")],
}

# ET-05 · the codes that name exactly ONE sub-vertical, and the aliases the
# manifest may spell them with. Mirrors apps/api/dma_api/subverticals.py —
# a family code (BK, WM) or a product line (PEN) names nobody and serves
# everyone.
SUBVERTICAL_CODES = ("RB", "CU", "CL", "CIB", "FC", "AM", "RIA", "IC", "IB")
SUBVERTICAL_ALIASES = {
    "RB": ("RB", "SV1", "REGIONAL BANKS", "RETAIL BANKING"),
    "CU": ("CU", "SV2", "CREDIT UNIONS", "CREDIT UNION"),
    "CL": ("CL", "SV3", "COMMERCIAL LENDING"),
    "CIB": ("CIB", "SV4", "CIB CAPITAL MARKETS", "CORP INVESTMENT BANKING",
            "CORPORATE INVESTMENT BANKING", "CIB BANKING"),
    "RIA": ("RIA", "SV5", "RIAS BROKER DEALERS", "RIA BROKER DEALER",
            "RIA BROKER DEALERS", "WEALTH RIAS"),
    "AM": ("AM", "SV6", "ASSET MANAGEMENT", "ASSET WEALTH MANAGEMENT",
           "WEALTH ASSET MANAGEMENT"),
    "IB": ("IB", "SV7", "INSURANCE BROKERS", "INSURANCE BROKERAGES"),
    "IC": ("IC", "SV8", "INSURANCE CARRIERS"),
    "FC": ("FC", "SV9", "FARM CREDIT", "FARM CREDIT AG LENDING"),
}
SUBVERTICAL_NAMES = {"RB": "retail banking", "CU": "credit unions",
                     "CL": "commercial lending", "CIB": "CIB / capital markets",
                     "FC": "farm credit", "AM": "asset and wealth management",
                     "RIA": "RIAs and broker-dealers", "IC": "insurance carriers",
                     "IB": "insurance brokers"}
VARIANT_SEGMENT = re.compile(r"^([A-Z]+)([0-9]+)$")
CELL_ID = re.compile(r"^P\d+C\d+\.")

problems: list[tuple[str, str, str]] = []


def bad(sev, path, msg):
    problems.append((sev, path, msg))


def walk(node, path=""):
    """Yield (path, value) for every scalar in the payload."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, node


def at_path(body, path):
    """Yield (json_path, value) for a `[*]`-walking spec path, at any depth."""
    head, sep, rest = path.partition("[*].")
    if not sep:
        node = body
        for part in head.split("."):
            if not isinstance(node, dict) or part not in node:
                return
            node = node[part]
        yield head, node
        return
    node = body
    for part in head.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    if isinstance(node, list):
        for i, item in enumerate(node):
            for sub, value in at_path(item, rest):
                yield f"{head}[{i}].{sub}", value


def variant_subvertical(cell):
    m = VARIANT_SEGMENT.match(str(cell).rsplit(".", 1)[-1])
    code = m.group(1) if m else None
    return code if code in SUBVERTICAL_CODES else None


def resolve_subvertical(raw):
    if not raw:
        return None
    norm = re.sub(r"[^A-Z0-9]+", " ", str(raw).upper()).strip()
    for code, aliases in SUBVERTICAL_ALIASES.items():
        if norm in aliases:
            return code
    return None


def sentence_case_offender(key, value):
    """→ the offending first word, or None. Same rule as CG-11."""
    if not isinstance(value, str) or len(value) < 25 or key in NEVER_SENTENCE:
        return None
    if not re.search(r"\s", value):
        return None
    text = value.strip().lstrip("\"'“‘([{")
    if not text or not text[0].isalpha() or not text[0].islower():
        return None
    if key not in PROSE_KEYS and value.strip()[-1] not in ".?!":
        return None
    word = text.split()[0].strip(".,;:")
    return None if CAMEL_FIRST_WORD.match(word) else word


def check_structure(page, payload):
    expected = set(SECTIONS[page])
    optional = OPTIONAL.get(page, set())
    got = set(payload)
    for missing in sorted(expected - got - optional):
        bad("BLOCK", page, f"required section '{missing}' is absent")
    for extra in sorted(got - expected):
        bad("BLOCK", f"{page}.{extra}", "section is not in this page's contract")
    for opt in sorted((expected & optional) - got):
        bad("INFO", f"{page}.{opt}", "optional section omitted")


def check_envelope(page, payload):
    for sec, body in payload.items():
        if not isinstance(body, dict):
            bad("BLOCK", f"{page}.{sec}", "section body must be an object")
            continue
        for field in ("produced_at", "producer_version", "e_ids"):
            if field not in body:
                bad("BLOCK", f"{page}.{sec}", f"universal envelope missing '{field}'")
        if sec in NEEDS_INTERNAL_ONLY and "internal_only" not in body:
            bad("BLOCK", f"{page}.{sec}",
                "client-visible section declares no internal_only paths — "
                "an unmarked internal rung reaches the client")
        eids = body.get("e_ids")
        if isinstance(eids, list):
            if len(eids) != len(set(eids)):
                bad("WARN", f"{page}.{sec}.e_ids", "contains duplicates")
            for e in eids:
                if isinstance(e, str) and not EID.fullmatch(e):
                    bad("BLOCK", f"{page}.{sec}.e_ids", f"'{e}' is not a valid evidence id")
                if isinstance(e, str) and (e.startswith("[") or e.endswith("]")):
                    bad("BLOCK", f"{page}.{sec}.e_ids",
                        f"'{e}' is bracketed — brackets belong to the chip, not the id")


def check_scalars(page, payload):
    for path, val in walk(payload, page):
        if not isinstance(val, str):
            continue
        low = path.lower()
        # Sentinels are VALUES, not words: a scalar whose whole content is
        # "N/A" or "null" is an unwritten field, but a 40-word sentence
        # describing a null ("completed_at and request_id are both null")
        # is prose doing its job. The old rule fired on the prose — four of
        # one run's six local blocks were this (MEM-0022) — so the sweep
        # now applies only to values short enough to BE a value.
        if len(val.split()) <= 6:
            for pat in SENTINELS:
                if re.search(pat, val):
                    bad("BLOCK", path,
                        f"sentinel value {val!r} — a derived value is "
                        "computed or null")
                    break
        # register rules on prose fields only — decided by the KEY, never by
        # the path (see is_prose_key)
        key = leaf_key(path)
        if is_prose_key(key):
            for pat, why in BANNED_REGISTER:
                if re.search(pat, val, re.I | re.M):
                    bad("WARN", path, f"{why}: matched /{pat}/")
            if not carries_ids(key) and re.search(r"\bP[1-4]C\d", val):
                bad("BLOCK", path, "raw taxonomy code in client-visible prose — "
                                   "humanise the capability name")
            if re.match(r"^\s*[A-Z0-9.]+\s+scores?\s+\d", val) or \
               re.match(r"^\s*(?:At|With)\s+\d\.\d", val):
                bad("WARN", path, "score-predicate opener")
            # Titles, headlines and card-face labels are claims, not
            # sentences — no terminal stop, and no clipped-text warning.
            is_label = key in LABEL_KEYS
            words = len(val.split())
            if val and not is_label and words >= PROSE_MIN_WORDS \
                    and val.strip()[-1] not in ".?!\"')]":
                bad("WARN", path, "prose does not end in terminal punctuation — "
                                  "clipped text was a measured defect")
            if is_label and words > 20:
                bad("WARN", path, f"label is {words} words — titles are claims, "
                                  "not sentences; keep them tight")
        # vocabularies
        if low.endswith(".tier") and val not in TIERS:
            bad("BLOCK", path, f"tier {val!r} outside T1–T5")
        if low.endswith("recency_tag") and val not in RECENCY:
            bad("BLOCK", path, f"recency {val!r} not in the one vocabulary")
        if low.endswith("claim_type") and val not in CLAIMS:
            bad("BLOCK", path, f"claim_type {val!r} unknown")
        if low.endswith(".layer") and val not in STACK_LAYERS:
            bad("BLOCK", path, f"layer {val!r} — use OPS/CUST/DATA/INFRA, never L2–L5 "
                               "(they collide with evidence levels)")
        if low.endswith(".status") and "techstack" in page and val not in STACK_STATUS:
            bad("BLOCK", path, f"stack status {val!r} unknown")
        if low.endswith(".result") and "gate" in low and val not in GATE_RESULT:
            bad("BLOCK", path, f"gate result {val!r} — must be PASS, FAIL or NOT_RUN")
        if low.endswith("peer_basis") and val not in PEER_BASIS:
            bad("BLOCK", path, f"peer_basis {val!r} unknown")
        if low.endswith("subcap_id") and not SUBCAP.match(val):
            bad("BLOCK", path, f"'{val}' is not a well-formed cell id")
        for field, pat in AGENT_IDS.items():
            if low.endswith(field) and not re.match(pat, val):
                bad("BLOCK", path, f"{field} {val!r} does not match {pat}")
        # excerpts — ET-04. An empty one is the refusal that matters: the id
        # resolves, so every other check passes, and the chip opens onto
        # nothing.
        if low.endswith(".excerpt"):
            n = len(val.strip())
            if n == 0:
                bad("BLOCK", path, "ET-04 empty excerpt — a citation with no "
                                   "verbatim span is a reference, not evidence")
            elif n < 50:
                bad("BLOCK", path, f"ET-04 excerpt is {n} chars — minimum 50")
            elif n > 500:
                bad("BLOCK", path, f"ET-04 excerpt is {n} chars — maximum 500")
            if val.strip().startswith("http"):
                bad("BLOCK", path, "excerpt is a bare URL, not a quotation")


def check_numbers(page, payload):
    for path, val in walk(payload, page):
        low = path.lower()
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if low.endswith("ers"):
                bad("WARN", path, "the server computes the rank score — sending it is ignored")
            if low.endswith(("score", "median")) and not (0 <= val <= 5):
                bad("BLOCK", path, f"{val} outside the 1–5 maturity scale")
            if low.endswith("_pct") and not (0 <= val <= 100):
                bad("BLOCK", path, f"{val} is not a percentage")
            if low.endswith("cohort_size") and val < 5:
                bad("BLOCK", path, f"cohort of {val} — below five it is not published")
        if val is None and low.endswith(("status", "severity")):
            bad("BLOCK", path, "status and severity are always populated")


def check_gates_section(page, payload):
    sg = payload.get("safeguard_gates")
    if not isinstance(sg, dict):
        return
    if "caps" not in sg or "gates" not in sg:
        bad("BLOCK", f"{page}.safeguard_gates",
            "must carry BOTH caps[] (what the assessment capped) and gates[] "
            "(the SG results) — they are different things")
    for i, g in enumerate(sg.get("gates", []) or []):
        p = f"{page}.safeguard_gates.gates[{i}]"
        if not g.get("plain_label"):
            bad("BLOCK", p, "plain_label is required — this card renders to the client")
        elif not 6 <= len(g["plain_label"].split()) <= 24:
            bad("WARN", p, "plain_label should be a human sentence of roughly 8–18 words")
        if g.get("result") == "NOT_RUN" and not g.get("not_run_reason"):
            bad("BLOCK", p, "NOT_RUN requires a reason — a silent NOT_RUN is a PASS in disguise")


def check_empty_states(page, payload):
    for sec, body in payload.items():
        if not isinstance(body, dict):
            continue
        arrays = {k: v for k, v in body.items() if isinstance(v, list)}
        # An H4-shaped section keeps its content in OBJECT MAPS (pillars,
        # categories keyed by id), so "every array is empty" can be true of
        # a fully populated section. The old rule flagged a workbook_scores
        # carrying 4 pillars and 17 categories as empty (MEM-0022); a
        # populated dict beside the empty arrays is content.
        populated_maps = any(isinstance(v, dict) and v
                             for k, v in body.items()
                             if k not in ("empty_state", "r_layer"))
        if arrays and all(len(v) == 0 for v in arrays.values()) \
                and not populated_maps:
            es = body.get("empty_state")
            if not es:
                bad("BLOCK", f"{page}.{sec}",
                    "every array is empty and no empty_state is declared — "
                    "an absence with no record is a research failure, not a finding")
            elif isinstance(es, dict) and not es.get("sources_searched"):
                bad("WARN", f"{page}.{sec}.empty_state",
                    "declares no sources_searched — state what established the absence")


def check_dating(page, payload):
    """CG-10 — the date that dates an item is a date or a recorded absence."""
    for sec, body in payload.items():
        entry = ITEM_DATING.get(sec)
        if not entry or not isinstance(body, dict):
            continue
        container, field, why = entry
        for i, item in enumerate(body.get(container) or []):
            if not isinstance(item, dict) or item.get(field) is not None:
                continue
            if item.get("quarantined") and item.get("quarantine_reason"):
                continue
            if any(str(item.get(f"{field}{s}") or "").strip()
                   for s in ("_basis", "_absence", "_note", "_reason")):
                continue
            if any(isinstance(item.get(k), str) and item[k].strip() in ABSENCE_RUNGS
                   for k in RUNG_KEYS):
                continue
            if any(item.get(k) for k in ("sources_searched", "queries_run")):
                continue
            bad("BLOCK", f"{page}.{sec}.{container}[{i}].{field}",
                f"CG-10 {field} is a bare null — {why}. State the date, carry "
                f"the rung that records the absence ({'/'.join(sorted(ABSENCE_RUNGS)[:4])}… "
                f"on {', '.join(RUNG_KEYS[:3])}, or the sources_searched "
                "ladder), or drop the row. The surface cannot tell 'nobody "
                "looked' from 'looked and found nothing'")


def check_sentence_case(page, payload):
    """CG-11 — every prose field begins with a capital, except a first word
    that carries an uppercase letter after its first character."""
    for path, val in walk(payload, page):
        key = leaf_key(path)
        word = sentence_case_offender(key, val if isinstance(val, str) else None)
        if word:
            bad("BLOCK", path,
                f"CG-11 begins {word!r} — a prose field on a client surface "
                f"begins with a capital. Write {word.capitalize()!r}. "
                "(nCino, iOS, eBay are exempt: an uppercase letter after the "
                "first character of the first word is the vendor's spelling.)")


def check_face_budgets(page, payload):
    """CG-12 — a chip, badge or single-line slot gets a label, not a
    paragraph. The repair is to MOVE the prose, never to trim it."""
    for sec, body in payload.items():
        if not isinstance(body, dict):
            continue
        for path, budget, slot, belongs in FACE_BUDGETS.get(sec, []):
            for jpath, val in at_path(body, path):
                if not isinstance(val, str) or not val.strip():
                    continue
                words, chars = len(val.split()), len(val)
                sents = len([s for s in re.split(r"(?<=[.!?])\s+", val.strip()) if s])
                over = None
                if "max_chars" in budget and chars > budget["max_chars"]:
                    over = f"{chars} characters against a budget of {budget['max_chars']}"
                elif "max_words" in budget and words > budget["max_words"]:
                    over = f"{words} words against a budget of {budget['max_words']}"
                elif "max_sentences" in budget and sents > budget["max_sentences"]:
                    over = f"{sents} sentences where the contract states {budget['max_sentences']}"
                elif "min_words" in budget and words < budget["min_words"]:
                    over = f"{words} words, under the stated floor of {budget['min_words']}"
                if over:
                    bad("BLOCK", f"{page}.{sec}.{jpath}",
                        f"CG-12 renders in {slot} and carries {over}. This "
                        f"field holds {belongs}. Move the prose, do not trim it")


def records_absence(item):
    """True when the item carries the LADDER that establishes an absence.

    The rungs are the record of what was reached: the sources searched, the
    queries run, the reason the reach fell short. Without them an empty
    citation list says only that nobody looked, which is a research failure
    and not a finding.
    """
    for key in ("sources_searched", "queries_run", "searches_run",
                "sources_checked", "search_ladder"):
        rungs = item.get(key)
        if isinstance(rungs, (list, tuple)) and any(str(r).strip() for r in rungs):
            return True
        if isinstance(rungs, str) and rungs.strip():
            return True
    return False


def claims_a_find(item):
    """True when the item says something WAS found.

    AG-03's own words: "a state claiming a find with an empty id list is a
    contradiction, not an empty state". Two shapes claim a find — a populated
    item list, and a `grounded_on` above zero, which invariant 8 defines as
    the LENGTH of the citation list and so cannot exceed it.
    """
    for key in ("items", "rows", "quotes", "excerpts", "spans", "hits",
                "matches", "findings"):
        found = item.get(key)
        if isinstance(found, (list, tuple)) and len(found) > 0:
            return True
    grounded = item.get("grounded_on")
    if isinstance(grounded, (int, float)) and not isinstance(grounded, bool):
        return grounded > 0
    return False


def asserts_nothing(item):
    """True when the item makes no claim, so no citation is owed.

    AG-03's registry text (apps/mcp/dma_mcp/gates.py) states the exemption in
    full: "A null-valued row and a recorded absence carrying its ladder assert
    nothing and are exempt; a state claiming a find with an empty id list is a
    contradiction, not an empty state." This checker implemented the first
    half and not the second, so it refused 629 cells of a run whose six pages
    all PASS the connector's gates — every one of them thin, grounded on
    nothing, and carrying six to eleven rungs of the search that established
    the absence. Each was a repair cycle billed against content that was
    already right.
    """
    if claims_a_find(item):
        return False
    if item.get("quarantined"):
        return True
    for key in ("state", "status", "basis", "peer_basis", "coverage", "result"):
        state = item.get(key)
        if isinstance(state, str) and state in ABSENT_STATES:
            # an absence is a finding only with the search that established it
            return records_absence(item)
    if records_absence(item):
        return True
    if item.get("empty_state"):
        return True
    return "value" in item and item.get("value") in (None, "")


def _cites(item, keys=EV_KEYS):
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return True
        if isinstance(v, list) and any(isinstance(x, str) and x.strip() for x in v):
            return True
    return False


def check_item_citations(page, payload):
    """AG-03 — every claim-bearing ITEM cites, not just the section.

    A card, signal, finding, ceiling or register row that asserts something
    about the institution and cites nothing is unfalsifiable: it renders to a
    client with no way back to a source. The envelope's `e_ids` is a union,
    not a substitute — a reader drills into the item.

    Two rules run. The first is the contract's: the item lists whose schema
    declares an evidence key must carry one on every asserting item. The
    second calibrates itself from the payload — where SOME items in a list
    cite and one does not, that one is the outlier, whatever the contract
    says, and it is the shape the defect actually takes.
    """
    for sec, body in payload.items():
        if not isinstance(body, dict):
            continue
        spec = ITEM_CITATIONS.get(sec)
        if spec:
            field, key = spec
            for i, item in enumerate(body.get(field) or []):
                if not isinstance(item, dict) or asserts_nothing(item):
                    continue
                if _cites(item, (key,)) or _cites(item):
                    continue
                bad("BLOCK", f"{page}.{sec}.{field}[{i}].{key}",
                    f"AG-03 this item asserts a claim and cites nothing — the "
                    f"{sec}.{field} item schema declares '{key}', and every "
                    "claim resolves to at least one registered id, inferences "
                    "included. Register the source and cite the id you were "
                    "given, or state the absence with its sources_searched "
                    "ladder. A find asserted with an empty id list is a "
                    "contradiction, not an empty state")
        # self-calibrating: a list where most items cite and one does not
        for field, items in body.items():
            if not isinstance(items, list) or len(items) < 3:
                continue
            objs = [x for x in items if isinstance(x, dict)]
            if len(objs) != len(items):
                continue
            citing = [x for x in objs if _cites(x)]
            if not (len(citing) >= 2 and len(citing) < len(objs)):
                continue
            if spec and spec[0] == field:
                continue        # already reported above, do not double-count
            for i, item in enumerate(objs):
                if _cites(item) or asserts_nothing(item):
                    continue
                bad("WARN", f"{page}.{sec}.{field}[{i}]",
                    f"AG-03 {len(citing)} of {len(objs)} items in this list "
                    "cite evidence and this one does not — the list's own "
                    "convention says it should. Cite it, or say why it "
                    "asserts nothing")


def check_contract_vocabularies(page, payload):
    """CG-09 — a closed vocabulary takes one of its values, including where
    the promoted column is plain TEXT and nothing downstream would notice."""
    for sec, body in payload.items():
        if not isinstance(body, dict):
            continue
        for path, values in CONTRACT_VOCABULARIES.get(sec, {}).items():
            for jpath, val in at_path(body, path):
                if val is None or val in values:
                    continue
                if isinstance(val, dict) and val.get("value") in values:
                    continue        # {value, clause} shape the contract allows
                shown = val if isinstance(val, str) and len(val) <= 60 else \
                    f"{str(val)[:57]}…"
                bad("BLOCK", f"{page}.{sec}.{jpath}",
                    f"CG-09 {shown!r} is not a value of this field — the "
                    f"contract states {' | '.join(values)}. Prose in an enum "
                    "slot promotes into a TEXT column, renders as itself, and "
                    "matches no filter: pick the value and put the sentence in "
                    "the field that carries prose")
        for path, values in LEADING_VOCABULARIES.get(sec, {}).items():
            for jpath, val in at_path(body, path):
                if val is None:
                    continue
                lead = val.get("value") if isinstance(val, dict) else val
                if isinstance(lead, str) and lead.strip() in values:
                    continue
                if isinstance(lead, str):
                    m = LEADING_TOKEN.match(lead.strip())
                    if m and m.group(0) in values:
                        continue
                shown = lead if isinstance(lead, str) and len(lead) <= 60 else \
                    f"{str(lead)[:57]}…"
                bad("BLOCK", f"{page}.{sec}.{jpath}",
                    f"CG-09 {shown!r} does not LEAD with one of "
                    f"{' | '.join(values)}. The clause of reasoning is the "
                    "contract's, but the value has to come first — the badge "
                    "prints the prefix and the filter reads it")


def check_required_item_fields(page, payload):
    for sec, rules in REQUIRED_ITEM_FIELDS.items():
        body = payload.get(sec)
        if not isinstance(body, dict):
            continue
        for field, key, sev, why in rules:
            for i, item in enumerate(body.get(field) or []):
                if not isinstance(item, dict):
                    continue
                val = item.get(key)
                if val is None or (isinstance(val, str) and not val.strip()):
                    bad(sev, f"{page}.{sec}.{field}[{i}].{key}",
                        f"required and absent — {why}")


def check_recommendation_shape(page, payload):
    """P2 anatomy the budgets cannot see: the two lists called
    'prerequisites', and the KPI that is not a KPI without its baseline."""
    body = payload.get("recommendations")
    if not isinstance(body, dict):
        return
    ids = set()
    for i, r in enumerate(body.get("recommendations") or []):
        if not isinstance(r, dict):
            continue
        p = f"{page}.recommendations.recommendations[{i}]"
        ids.add(r.get("rec_id"))
        kpi = r.get("kpi_triple")
        if isinstance(kpi, dict):
            for k in ("metric", "baseline", "target"):
                if not str(kpi.get(k) or "").strip():
                    bad("BLOCK", f"{p}.kpi_triple.{k}",
                        "a KPI triple renders metric, Baseline and Target as "
                        "three lines; one of them empty renders a metric with "
                        "no way to tell whether it moved")
            if kpi.get("baseline") and not kpi.get("baseline_as_of"):
                bad("WARN", f"{p}.kpi_triple.baseline_as_of",
                    "the baseline must be a figure that EXISTS in the pack "
                    "with an as_of, not an aspiration — the card prints the "
                    "date beside it")
        for j, q in enumerate(r.get("prerequisites") or []):
            if not isinstance(q, dict):
                continue
            qp = f"{p}.prerequisites[{j}]"
            if q.get("cell"):
                if q.get("minimum") is None or q.get("current") is None:
                    bad("BLOCK", qp,
                        "a cell-shaped prerequisite draws a progress bar "
                        "against its minimum and a MET/NOT MET verdict from "
                        "the pair — send {cell, minimum, current, verdict} or "
                        "send the text shape {condition, basis, note}")
            elif not q.get("condition"):
                bad("BLOCK", qp,
                    "a prerequisite is either a cell threshold "
                    "{cell, minimum, current, verdict} or a text condition "
                    "{condition, basis, note}. This row is neither, so the "
                    "readiness card cannot key it and drops it")
        gate = r.get("validation_gate")
        if isinstance(gate, dict) and not gate.get("backing_cells"):
            bad("WARN", f"{p}.validation_gate.backing_cells",
                "the readiness drilldown renders the backing cells — a "
                "verdict with none is a claim the reader cannot trace")
    for i, r in enumerate(body.get("recommendations") or []):
        for dep in (r.get("dependencies") or []) if isinstance(r, dict) else []:
            if dep not in ids:
                bad("BLOCK",
                    f"{page}.recommendations.recommendations[{i}].dependencies",
                    f"'{dep}' is not a rec_id in this page — the modal's "
                    "Sequencing tab resolves dependencies both ways and "
                    "renders an empty Prerequisites column instead")


def cell_citations(page, payload):
    """(path, key, cell_id) for every catalogue cell a payload cites."""
    for path, val in walk(payload, page):
        key = leaf_key(path)
        if isinstance(val, str) and CELL_ID.match(val) and \
                (key.endswith("subcap_ids") or key == "subcap_id"):
            yield path, key, val


def check_subvertical_scope(page, payload, subvertical):
    """ET-05 — no section cites a variant cell belonging to somebody else."""
    if not subvertical:
        bad("INFO", page, "ET-05 not run — pass --subvertical to check that "
                          "no cited cell belongs to another sub-vertical")
        return
    code = resolve_subvertical(subvertical)
    if code is None:
        bad("WARN", page, f"ET-05 not run — {subvertical!r} is in neither "
                          "vocabulary (SV1-SV9 or RB/CU/CL/CIB/FC/AM/RIA/IC/IB)")
        return
    seen = set()
    for path, _key, cell in cell_citations(page, payload):
        owner = variant_subvertical(cell)
        if owner is None or owner == code or cell in seen:
            continue
        seen.add(cell)
        bad("BLOCK", path,
            f"ET-05 {cell} is a {SUBVERTICAL_NAMES[owner]} variant cell and "
            f"this run is {SUBVERTICAL_NAMES[code]} — the terminal segment "
            "names its owner. The workbook measuring it is a fact; serving it "
            "here is not. Drop the cell, and the sentence resting on it")


def check_cell_linkage(page, payload, cells):
    """CG-14 — every linked cell exists on this run."""
    if cells is None:
        bad("INFO", page, "CG-14 not run — pass --cells to resolve every "
                          "linked cell against the run's own scored set")
        return
    seen = set()
    for path, key, cell in cell_citations(page, payload):
        if cell in cells or cell in seen:
            continue
        seen.add(cell)
        bad("BLOCK", path,
            f"CG-14 {key} names {cell}, which this run does not carry — the "
            "chip renders and opens the cell drawer onto nothing. Link a cell "
            "the run carries, or drop the link and say what the row bears on "
            "in prose")


def load_cells(spec):
    """A bundle JSON, a subcaps response, or a bare list of cell ids."""
    if not spec:
        return None
    data = json.load(open(spec, encoding="utf-8"))
    if isinstance(data, list):
        return {x if isinstance(x, str) else x.get("subcap_id") for x in data}
    for key in ("subcaps", "scores", "subcap_scores"):
        rows = data.get(key)
        if isinstance(rows, list):
            return {r.get("subcap_id") for r in rows if isinstance(r, dict)}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("payload")
    ap.add_argument("--page", required=True, choices=sorted(SECTIONS))
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument("--subvertical", help="the ENTITY's sub-vertical (SV2, CU, "
                                          "'Credit Unions') — turns on ET-05")
    ap.add_argument("--cells", help="bundle JSON or list of the run's cell ids "
                                    "— turns on CG-14")
    a = ap.parse_args()

    try:
        payload = json.load(open(a.payload, encoding="utf-8"))
    except Exception as e:
        print(f"could not read payload: {e}")
        return 1
    if not isinstance(payload, dict):
        print("payload must be an object keyed by section name")
        return 1

    try:
        cells = load_cells(a.cells)
    except Exception as e:
        print(f"could not read --cells: {e}")
        return 1

    for fn in (check_structure, check_envelope, check_scalars, check_numbers,
               check_gates_section, check_empty_states, check_dating,
               check_sentence_case, check_face_budgets, check_item_citations,
               check_contract_vocabularies, check_required_item_fields,
               check_recommendation_shape):
        fn(a.page, payload)
    check_subvertical_scope(a.page, payload, a.subvertical)
    check_cell_linkage(a.page, payload, cells)

    order = {"BLOCK": 0, "WARN": 1, "INFO": 2}
    problems.sort(key=lambda p: (order[p[0]], p[1]))
    blocks = sum(1 for s, *_ in problems if s == "BLOCK")
    warns = sum(1 for s, *_ in problems if s == "WARN")

    print(f"page: {a.page}   sections: {len(payload)}   "
          f"blocking: {blocks}   warnings: {warns}\n")
    for sev, path, msg in problems:
        print(f"  [{sev:5s}] {path}\n            {msg}")
    if not problems:
        print("  clean — the local checks pass. Grain, identity and grounding are still "
              "checked server-side at submit.")
    return 1 if blocks or (a.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())
