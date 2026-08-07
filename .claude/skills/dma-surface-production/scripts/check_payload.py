#!/usr/bin/env python3
"""Local pre-submit checks for a DMA Insights page payload.

Catches the cheap failures here so submissions spend their round trips on the
expensive ones — grain, identity and grounding — which only the server can check.

    python scripts/check_payload.py payload.json --page overview
    python scripts/check_payload.py payload.json --page heatmap --strict
    python scripts/check_payload.py payload.json --page heatmap \
        --subvertical SV2 --cells bundle.json

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
SUBCAP = re.compile(r"^P[1-4]C\d{1,2}(?:\.\d{1,2}){0,2}[a-z]?$")
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
NEVER_SENTENCE = {
    "excerpt", "quote", "verbatim", "snippet", "url", "source_url",
    "linkedin_url", "producer_version", "source_domain", "domain", "email",
    "phone", "e_id", "source_name", "vendor", "product", "name", "field",
    "unit", "value", "kind", "layer", "status", "tier", "id",
}
CAMEL_FIRST_WORD = re.compile(r"^[a-z]+[A-Z]")     # nCino, iOS, eBay

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
        # sentinels anywhere
        for pat in SENTINELS:
            if re.search(pat, val):
                bad("BLOCK", path,
                    f"sentinel value {val!r} — a derived value is computed or null")
                break
        # register rules on prose fields only
        if any(k in low for k in ("body", "rationale", "story", "text", "framing",
                                  "synthesis", "summary", "title", "headline",
                                  "statement", "narrative", "consequence")):
            for pat, why in BANNED_REGISTER:
                if re.search(pat, val, re.I | re.M):
                    bad("WARN", path, f"{why}: matched /{pat}/")
            if re.search(r"\bP[1-4]C\d", val):
                bad("BLOCK", path, "raw taxonomy code in client-visible prose — "
                                   "humanise the capability name")
            if re.match(r"^\s*[A-Z0-9.]+\s+scores?\s+\d", val) or \
               re.match(r"^\s*(?:At|With)\s+\d\.\d", val):
                bad("WARN", path, "score-predicate opener")
            # Titles and headlines are labels, not sentences — no terminal stop.
            is_label = any(low.endswith(x) for x in (".title", ".headline", ".statement"))
            if val and not is_label and val.strip()[-1] not in ".?!\"')]":
                bad("WARN", path, "prose does not end in terminal punctuation — "
                                  "clipped text was a measured defect")
            if is_label and len(val.split()) > 20:
                bad("WARN", path, f"label is {len(val.split())} words — titles are claims, "
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
        if arrays and all(len(v) == 0 for v in arrays.values()):
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
        key = path.rsplit(".", 1)[-1].split("[")[0]
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


def cell_citations(page, payload):
    """(path, key, cell_id) for every catalogue cell a payload cites."""
    for path, val in walk(payload, page):
        key = path.rsplit(".", 1)[-1].split("[")[0]
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
               check_sentence_case, check_face_budgets):
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
