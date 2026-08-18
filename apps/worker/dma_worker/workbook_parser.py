"""Scoring-workbook parser (stage 1.3) — the two fields that cannot be
backfilled originate here: the workbook cell each score was read from,
and (upstream) the artefact bytes.

Shape (Claude-DMA generation, learned from a real fixture):
- `2_Scorecard` carries a "Subcapability scorecard" section — one row per
  assessed subcap with Effective_Score, the SERVED score. Scores are READ
  from the workbook, never re-derived (Backend Schema §04); source_cell
  records exactly which cell ("2_Scorecard!S16").
- `3_Assessment` carries one row per facet (Question_ID = subcap + facet
  suffix) with per-facet score, evidence quality, E-id references and the
  assessor's rationale — the grounding detail behind each subcap row.

Three row states, three different meanings:
- scored             → a subcap_scores row with source_cell + grain ids
- attempted, unscored ("NO_EVIDENCE - ladder run" / missing Effective_Score)
                     → SKIPPED, never defaulted to zero, with a parser
                       observation (a zero renders as the lowest band and
                       is indistinguishable from a real assessment)
- toggled out        → variant cells whose facet rows are entirely empty:
                       excluded by the sub-vertical toggle cascade. Not an
                       observation — they are WHY scored_cells differs
                       from catalogue_cells.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import openpyxl

SUBCAP_RE = re.compile(r"^P\d+C\d+(?:\.(?:\d+|[A-Z]+\d+))+$")
GRAIN_RE = re.compile(r"^(P\d+)(C\d+)\.(\d+|[A-Z]+\d+)")
# Two evidence-id families, both published by the upstream dma-assessment
# skill's column spec (`references/workbook_specification.md` §Column F):
# `E-\d{3}` for public evidence and `INT-[DOC_ABBREV]-\d{3}` for internal
# documents the client supplied. The internal form was unmatched here, so
# every INT- citation was dropped without an observation — 341 of them in
# one shipped package (ATB), whose cells then read as uncited.
EID_RE = re.compile(r"\b(?:E-[A-Z]{0,3}\d{2,4}(?::F\d+)?|INT-[A-Z0-9]{2,12}-\d{1,4}(?::F\d+)?)\b")

# The rubric the whole product bands on is M1–M5. A workbook cell outside it
# is not a score at a different scale, it is a defect: 0 renders as the lowest
# band and is indistinguishable from a real assessment of "barely started".
SCORE_MIN, SCORE_MAX = Decimal("1"), Decimal("5")


def _norm(name: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", str(name).strip())).strip("_").lower()


def _grain(subcap_id: str):
    m = GRAIN_RE.match(subcap_id)
    if not m:
        return None, None, None
    pillar = m.group(1)
    return pillar, pillar + m.group(2), f"{pillar}{m.group(2)}.{m.group(3)}"


def _decimal(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        return "UNPARSEABLE"


@dataclass
class ParsedFacet:
    question_id: str
    facet: str
    score: Decimal | None
    source_cell: str
    evidence_quality: Decimal | None
    contradiction_status: str | None
    rationale: str | None
    evidence_refs: list


@dataclass
class ParsedScore:
    subcap_id: str
    pillar_id: str
    category_id: str
    capability_id: str
    name: str | None
    tier: str | None
    score: Decimal
    source_cell: str
    evidence_quality: Decimal | None
    confidence: str | None = None      # HIGH · MEDIUM · LOW where the workbook carries it
    facets: list = field(default_factory=list)
    evidence_refs: list = field(default_factory=list)
    rationale: str | None = None       # scorer's grounding text; embedded, never stored


@dataclass
class Observation:
    kind: str          # missing_score · unparseable_cell · column_not_found · …
    subcap_id: str
    detail: dict


def _column_not_found(tab: str, field: str, tried, headers) -> Observation:
    """The observation an unrecognised column MUST produce.

    A reader that does not recognise its input carries on as though the input
    were empty, and a null column is indistinguishable from a column of nulls.
    So every lookup that fails names the tab, the field it was looking for,
    the spellings it accepts and the headers actually present — enough for the
    next spelling to be added without reading the workbook first.
    """
    return Observation("column_not_found", None, {
        "tab": tab, "field": field, "expected_any_of": list(tried),
        "headers_present": sorted(headers)[:30]})


def _pick_col(headers: dict, names) -> int | None:
    """First alias present wins; None when the column is not there at all."""
    for n in names:
        if n in headers:
            return headers[n]
    return None


# Column spellings the shipped corpus uses, per field. Measured across the 153
# packages under the production intake tree — `scoring_rationale` alone appears
# in 35 scoring tabs across 9 clients, and matching "rationale" by PREFIX
# missed every one of them, losing the only verbatim excerpt text the
# general_dma generation carries.
_EVIDENCE_ID_KEYS = ("evidence_ids", "evidence_id", "evidence_refs",
                     "evidence_references", "e_ids", "evidence_ids_cited",
                     "citations", "evidence")
_RATIONALE_KEYS = ("rationale", "scoring_rationale", "assessor_rationale",
                   "score_rationale", "rationale_150_chars", "justification",
                   "rationale_evidence", "scoring_notes", "evidence_rationale",
                   "narrative")


@dataclass
class WorkbookParse:
    scores: list
    observations: list
    toggled_out: list           # variant cells excluded by the toggle cascade
    scored_cells: int = 0
    composite: Decimal | None = None
    composite_source_cell: str | None = None


def _header_map(ws, anchor: str, marker: str | None = None, max_scan: int = 30):
    """Find the header row (optionally only after a section marker row) and
    return ({normalised name: 0-based col}, first_data_row)."""
    seen_marker = marker is None
    for r, row in enumerate(ws.iter_rows(min_row=1, max_row=max_scan, values_only=True), 1):
        if not seen_marker:
            if any(v and marker.lower() in str(v).lower() for v in row):
                seen_marker = True
            continue
        names = {}
        for i, v in enumerate(row):
            if v is not None and str(v).strip():
                names.setdefault(_norm(v), i)
        if _norm(anchor) in names:
            return names, r + 1
    raise ValueError(f"header row with {anchor!r} not found (marker={marker!r})")


def parse_scoring_workbook(path: str) -> WorkbookParse:
    """Two shipped generations, detected by tab set:
    - claude_dma:  2_Scorecard (Effective_Score) + 3_Assessment facets
    - general_dma: P{n}_Subcap_Scoring tabs (one row per subcap) +
                   Evidence_Master / Peer_Benchmarks (parsed separately)
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if "2_Scorecard" in wb.sheetnames:
            facets = _parse_assessment(wb["3_Assessment"]) if "3_Assessment" in wb.sheetnames else {}
            return _parse_scorecard(wb["2_Scorecard"], facets)
        pillar_tabs = [t for t in wb.sheetnames if _is_pillar_tab(t)]
        if pillar_tabs:
            out = _parse_pillar_scoring(wb, pillar_tabs)
            if not out.scores and not out.observations and not out.toggled_out:
                # Structurally impossible to reach silently: a workbook whose
                # pillar tabs yielded nothing at all still names itself.
                out.observations.append(Observation(
                    "workbook_yielded_nothing", None,
                    {"tabs_read": sorted(pillar_tabs),
                     "reason": "pillar-grain tabs were found and read, and no "
                               "cell, observation or toggled-out variant came "
                               "out of any of them"}))
            return out
        # Rollup-only variant: recognisably a DMA workbook (stated pillar/
        # category grains present) but carrying no subcap-grain tabs at
        # all. The package lands with zero scored cells and its stated
        # grains — recorded, never guessed, never a crash-requeue loop.
        if "Pillar_Summary" in wb.sheetnames or "Category_Detail" in wb.sheetnames:
            out = WorkbookParse(scores=[], observations=[], toggled_out=[])
            out.observations.append(Observation(
                "no_subcap_grain_tabs", None,
                {"tabs": list(wb.sheetnames)[:20],
                 "note": "rollup-only workbook: stated grains land, no cells"}))
            out.scored_cells = 0
            return out
        # A generation nobody has taught this parser. Raising is deliberate:
        # the caller records it and quarantines the package by name after
        # three attempts, which is louder than a run with no cells. The
        # message is the quarantine reason, so it names what was looked for.
        raise ValueError(
            "unrecognised scoring workbook generation: "
            f"tabs={wb.sheetnames}; expected one of "
            "'2_Scorecard' (claude_dma), a P<n>_* subcapability tab "
            "(general_dma), or 'Pillar_Summary'/'Category_Detail' "
            "(rollup-only)")
    finally:
        wb.close()


CONFIDENCE_WORDS = {"HIGH", "MEDIUM", "LOW"}


# Score-column names across the shipped variants, in preference order —
# post-critic beats pre-critic where a critic pass shipped both.
_SCORE_KEYS = ("score", "post_critic_score", "score_1_to_5",
               "effective_score", "final_score")
_NAME_KEYS = ("subcap_name", "subcapability", "sub_cap_name")


# Which pillar tab wins when a workbook carries more than one for the same
# pillar, most authoritative first. Matched as a substring of the lowercased
# tab name; anything unlisted ranks last, in tab order.
#
# MEASURED, not assumed. 23 of the 154 corpus workbooks are MERGED files
# carrying both the assessment's `P{n}_Subcap_Scoring` and the research
# layer's `P{n}_Scoring_Detail`, so the parser read every cell twice: 1,420
# rows for a 710-cell assessment. Which tab is authoritative was settled by
# asking the workbook: aggregating `P*_Subcap_Scoring` reproduces its own
# `Pillar_Summary` (2.13 / 2.45 / 2.08 / 2.26 against a stated 2.13 / 2.44 /
# 2.08 / 2.25), and `_Scoring_Detail` is the calculation chain behind it —
# pre-critic, intermediate, and not what the summary sheets cite.
# Most specific FIRST — every token must be reachable. `scoring_detail`
# contains `scoring`, so listing the generic one earlier would make the
# specific one dead and rank the research tab as though it were the
# assessment's.
_TAB_PRECEDENCE = ("subcap_scoring", "subcapability_scoring",
                   "scoring_detail", "detail", "scoring")


def _tab_rank(tab: str) -> int:
    low = tab.lower()
    for i, token in enumerate(_TAB_PRECEDENCE):
        if token in low:
            return i
    return len(_TAB_PRECEDENCE)


def _dedupe_scores(result: "WorkbookParse") -> None:
    """One score per cell, chosen by tab authority rather than by row order.

    23 of the 154 corpus workbooks are MERGED files carrying both the
    assessment's `P{n}_Subcap_Scoring` and the research layer's
    `P{n}_Scoring_Detail`, so this parser emitted two `ParsedScore` rows per
    cell — 1,420 for a 710-cell assessment, 12,461 redundant rows across the
    corpus.

    WHAT WAS ALREADY SAFE, stated so this is not read as a bigger fix than it
    is. `persist` deduplicates on its own (`seen_subcaps`, first row wins,
    the repeat recorded as `duplicate_subcap_row` carrying its skipped
    score), and it counts `len({s.subcap_id ...})`, so the run's stored cell
    count was never inflated and no duplicate row was ever inserted twice.

    WHAT THIS CHANGES, and it is three narrower things:

      * `WorkbookParse.scored_cells` was the raw row count, so the parse
        result reported 1,420 cells for an assessment that scored 710. Only
        logging and intake status read it, but a field that disagrees with
        the database by a factor of two is a trap for the next reader.
      * persist's first-wins is ALPHABETICAL — `sorted()` puts
        `P2_Scoring_Detail` ahead of `P2_Subcap_Scoring`, so the research
        calculation chain outranked the tab the workbook's own
        `Pillar_Summary` agrees with. Measured, the two tabs never disagree
        today (13 disagreements, all of them two rows on ONE sheet), so
        nothing served was wrong — but the precedence was accidental, and
        the next merged generation would have inherited it.
      * a benign repeat and a genuine contradiction were the same
        observation kind. They are now `superseded_duplicate` and
        `duplicate_score_disagreement`, because a workbook stating one cell
        twice with two different scores is a finding about the workbook.
    """
    best: dict = {}
    for score in result.scores:
        tab = (score.source_cell or "").split("!")[0]
        rank = _tab_rank(tab)
        prior = best.get(score.subcap_id)
        if prior is None:
            best[score.subcap_id] = (rank, score)
            continue
        prior_rank, prior_score = prior
        keep, drop = ((prior_score, score) if prior_rank <= rank
                      else (score, prior_score))
        if str(prior_score.score) != str(score.score):
            result.observations.append(Observation(
                "duplicate_score_disagreement", score.subcap_id, {
                    "kept": {"source_cell": keep.source_cell,
                             "score": str(keep.score)},
                    "dropped": {"source_cell": drop.source_cell,
                                "score": str(drop.score)},
                    "resolution": "the tab the workbook's own Pillar_Summary "
                                  "agrees with is authoritative; the other "
                                  "reading is recorded, not averaged"}))
        else:
            result.observations.append(Observation(
                "superseded_duplicate", score.subcap_id,
                {"kept": keep.source_cell, "dropped": drop.source_cell}))
        best[score.subcap_id] = (min(prior_rank, rank), keep)
    if len(best) != len(result.scores):
        # Order is meaning (rule 10): keep first-seen order, not dict order.
        seen, ordered = set(), []
        for score in result.scores:
            if score.subcap_id in seen:
                continue
            seen.add(score.subcap_id)
            ordered.append(best[score.subcap_id][1])
        result.scores = ordered


def _parse_pillar_scoring(wb, pillar_tabs) -> WorkbookParse:
    result = WorkbookParse(scores=[], observations=[], toggled_out=[])
    for tab in sorted(pillar_tabs):
        ws = wb[tab]
        headers = first = None
        for anchor in ("SubCap_ID", "Sub_Cap_ID", "SubCapability_ID", "Subcap ID"):
            try:
                headers, first = _header_map(ws, anchor)
                break
            except ValueError:
                continue
        if headers is None:
            # A pillar-shaped tab with no subcapability header is a rollup
            # or a layout this parser does not read: recorded, never fatal.
            result.observations.append(Observation(
                "unrecognised_pillar_tab", None, {"tab": tab}))
            continue
        sid_col = next((headers[k] for k in
                        ("subcap_id", "sub_cap_id", "subcapability_id", "subcap")
                        if k in headers), None)
        if sid_col is None:
            result.observations.append(Observation(
                "unrecognised_pillar_tab", None, {"tab": tab}))
            continue
        score_col = next((headers[k] for k in _SCORE_KEYS if k in headers), None)
        if score_col is None:
            result.observations.append(Observation(
                "missing_score_column", None,
                {"tab": tab, "headers": sorted(headers)[:20]}))
            continue
        score_letter = openpyxl.utils.get_column_letter(score_col + 1)
        conf_col = headers.get("confidence")
        name_col = next((headers[k] for k in _NAME_KEYS if k in headers), None)
        eids_col = _pick_col(headers, _EVIDENCE_ID_KEYS)
        if eids_col is None:
            result.observations.append(
                _column_not_found(tab, "evidence_ids", _EVIDENCE_ID_KEYS, headers))
        rationale_col = _pick_col(headers, _RATIONALE_KEYS)
        if rationale_col is None:  # e.g. "Rationale (≥150 chars)"
            rationale_col = next((v for k, v in sorted(headers.items())
                                  if "rationale" in k), None)
        if rationale_col is None:
            result.observations.append(
                _column_not_found(tab, "rationale", _RATIONALE_KEYS, headers))
        id_col_header = next((k for k, v in headers.items() if v == sid_col), "?")
        seen_ids = unrecognised = 0
        samples: list = []
        for r, row in enumerate(ws.iter_rows(min_row=first, values_only=True), first):
            def cell_at(i, _row=row):
                return _row[i] if i is not None and i < len(_row) else None
            sid = cell_at(sid_col)
            sid = str(sid).strip() if sid else None
            if not sid:
                continue
            seen_ids += 1
            if not SUBCAP_RE.match(sid):
                unrecognised += 1
                if len(samples) < 5 and sid not in samples:
                    samples.append(sid)
                continue
            pillar, category, capability = _grain(sid)
            score = _decimal(cell_at(score_col))
            cell = f"{tab}!{score_letter}{r}"
            if score == "UNPARSEABLE":
                result.observations.append(Observation(
                    "unparseable_cell", sid, {"source_cell": cell,
                                              "raw": str(cell_at(score_col))[:80]}))
                continue
            refs_raw = str(cell_at(eids_col) or "")
            rationale = (str(cell_at(rationale_col)).strip()
                         if cell_at(rationale_col) else None)
            if score is None:
                if refs_raw.strip() or rationale:
                    result.observations.append(Observation(
                        "missing_score", sid, {"source_cell": cell}))
                else:
                    result.toggled_out.append(sid)
                continue
            if not (SCORE_MIN <= score <= SCORE_MAX):
                # Out of the M1–M5 rubric: never stored, never rescaled. A 0
                # banded as Activating and a 7 banded as Differentiating are
                # both real maturity on the heatmap, and neither was assessed.
                result.observations.append(Observation(
                    "score_out_of_range", sid,
                    {"source_cell": cell, "stated": str(score),
                     "rubric": f"{SCORE_MIN}–{SCORE_MAX}",
                     "resolution": "cell not scored; the workbook states a "
                                   "value outside the maturity rubric"}))
                continue
            conf = None
            if cell_at(conf_col) is not None:
                c = str(cell_at(conf_col)).strip().upper()
                conf = c if c in CONFIDENCE_WORDS else None
            result.scores.append(ParsedScore(
                subcap_id=sid, pillar_id=pillar, category_id=category,
                capability_id=capability,
                name=(str(cell_at(name_col)).strip() if cell_at(name_col) else None),
                tier=None, score=score, source_cell=cell,
                evidence_quality=None, confidence=conf,
                facets=[], evidence_refs=sorted({m.split(":")[0] for m in EID_RE.findall(refs_raw)}),
                rationale=rationale,
            ))
        if seen_ids and unrecognised == seen_ids:
            # THE silent-zero case. Two shipped packages (American Homes,
            # Wescom Financial) state CATEGORY ids — `P1C1` — in the
            # SubCap_ID column of a subcapability tab, so 1,401 populated
            # rows matched nothing and the whole workbook parsed to zero
            # scores, zero observations and zero toggled-out cells: a record
            # indistinguishable from an assessment nobody had done. A shape
            # the parser cannot read is a named refusal, never an empty tab.
            result.observations.append(Observation(
                "unrecognised_cell_id_format", None, {
                    "tab": tab, "column": id_col_header,
                    "expected": SUBCAP_RE.pattern,
                    "found_examples": samples,
                    "rows_dropped": unrecognised,
                    "reason": "every populated id on this tab failed the "
                              "subcapability id pattern; no cell could be "
                              "attributed, so none was scored"}))
    # One score per cell, BEFORE the count is taken — `scored_cells` is what
    # the directory reports as a run's coverage, so counting duplicates
    # overstates every merged workbook by the size of its second tab set.
    _dedupe_scores(result)
    result.scored_cells = len(result.scores)
    return result


def _parse_assessment(ws) -> dict:
    headers, first = _header_map(ws, "Sub_Cap_ID")
    col = {k: headers.get(k) for k in
           ("question_id", "sub_cap_id", "facet", "facet_maturity_score",
            "evidence_quality", "contradiction_status", "assessor_rationale",
            "evidence_references")}
    per_subcap: dict[str, list[ParsedFacet]] = {}
    for r, row in enumerate(ws.iter_rows(min_row=first, values_only=True), first):
        sid = row[col["sub_cap_id"]] if col["sub_cap_id"] is not None else None
        sid = str(sid).strip() if sid else None
        if not sid or not SUBCAP_RE.match(sid):
            continue
        def v(key):
            i = col.get(key)
            return row[i] if i is not None and i < len(row) else None
        score = _decimal(v("facet_maturity_score"))
        score_col_letter = openpyxl.utils.get_column_letter(col["facet_maturity_score"] + 1)
        refs_raw = str(v("evidence_references") or "")
        per_subcap.setdefault(sid, []).append(ParsedFacet(
            question_id=str(v("question_id") or ""),
            facet=str(v("facet") or ""),
            score=None if score == "UNPARSEABLE" else score,
            source_cell=f"3_Assessment!{score_col_letter}{r}",
            evidence_quality=None if (eq := _decimal(v("evidence_quality"))) == "UNPARSEABLE" else eq,
            contradiction_status=(str(v("contradiction_status")).strip() or None) if v("contradiction_status") else None,
            rationale=(str(v("assessor_rationale")).strip() or None) if v("assessor_rationale") else None,
            evidence_refs=EID_RE.findall(refs_raw),
        ))
    return per_subcap


def _parse_scorecard(ws, facets: dict) -> WorkbookParse:
    result = WorkbookParse(scores=[], observations=[], toggled_out=[])

    # The hero composite: the cell under "Overall Effective Score".
    label_at = None
    for r, row in enumerate(ws.iter_rows(min_row=1, max_row=12, values_only=True), 1):
        for i, v in enumerate(row):
            if v and _norm(v) == "overall_effective_score":
                label_at = (r, i)
        if label_at and r == label_at[0] + 1:
            i = label_at[1]
            comp = _decimal(row[i] if i < len(row) else None)
            if comp not in (None, "UNPARSEABLE"):
                result.composite = comp
                result.composite_source_cell = f"2_Scorecard!{openpyxl.utils.get_column_letter(i + 1)}{r}"

    headers, first = _header_map(ws, "Effective_Score", marker="Subcapability scorecard")
    sid_col = headers["sub_cap_id"]
    score_col = headers["effective_score"]
    eq_col = headers.get("evidence_quality")
    name_col = headers.get("sub_cap_name")
    tier_col = headers.get("tier")
    score_letter = openpyxl.utils.get_column_letter(score_col + 1)

    for r, row in enumerate(ws.iter_rows(min_row=first, values_only=True), first):
        sid = row[sid_col] if sid_col < len(row) else None
        sid = str(sid).strip() if sid else None
        if not sid or not SUBCAP_RE.match(sid):
            continue
        pillar, category, capability = _grain(sid)
        sub_facets = facets.get(sid, [])
        score = _decimal(row[score_col] if score_col < len(row) else None)

        if score == "UNPARSEABLE":
            result.observations.append(Observation(
                "unparseable_cell", sid,
                {"source_cell": f"2_Scorecard!{score_letter}{r}",
                 "raw": str(row[score_col])[:80]}))
            continue
        if score is None:
            attempted = any(f.score is not None or f.evidence_refs or
                            "NO_EVIDENCE" in str(f.rationale or "") for f in sub_facets) or any(
                            "NO_EVIDENCE" in str(getattr(f, "rationale", "") or "") for f in sub_facets)
            # Distinguish attempted-but-unscored from toggled-out variants:
            # a toggled-out cell has NO facet content at all.
            has_any_facet_content = any(
                f.score is not None or f.evidence_refs or f.rationale for f in sub_facets)
            if has_any_facet_content or attempted:
                result.observations.append(Observation(
                    "missing_score", sid,
                    {"source_cell": f"2_Scorecard!{score_letter}{r}",
                     "facets_with_content": sum(1 for f in sub_facets
                                                if f.score is not None or f.evidence_refs)}))
            else:
                result.toggled_out.append(sid)
            continue

        refs = sorted({e for f in sub_facets for e in f.evidence_refs})
        eq = _decimal(row[eq_col]) if eq_col is not None and eq_col < len(row) else None
        result.scores.append(ParsedScore(
            subcap_id=sid, pillar_id=pillar, category_id=category,
            capability_id=capability,
            name=(str(row[name_col]).strip() if name_col is not None and row[name_col] else None),
            tier=(str(row[tier_col]).strip() if tier_col is not None and row[tier_col] else None),
            score=score, source_cell=f"2_Scorecard!{score_letter}{r}",
            evidence_quality=None if eq == "UNPARSEABLE" else eq,
            facets=sub_facets, evidence_refs=refs,
        ))

    result.scored_cells = len(result.scores)
    return result


# ── General-DMA companion tabs ─────────────────────────────────────────

DATE_FUZZY = re.compile(r"^(\d{4})(?:-(?:Q([1-4])|(\d{2})))?")


def parse_fuzzy_date(value):
    """'2025-07' → 2025-07-01; '2025-Q4' → quarter END (H7 rule); '2025' →
    None is NOT returned for a bare year — the year is a date at year grain,
    resolved to Jan 1 conservatively. Unparseable → None (UNVERIFIED)."""
    if value is None:
        return None
    from datetime import date
    m = DATE_FUZZY.match(str(value).strip())
    if not m:
        return None
    try:
        year = int(m.group(1))
        if m.group(2):
            q = int(m.group(2))
            month, day = 3 * q, (31, 30, 30, 31)[q - 1]
            return date(year, month, day)
        if m.group(3):
            return date(year, int(m.group(3)), 1)
        return date(year, 1, 1)
    except ValueError:
        # e.g. "2025-13" — a month that isn't one. Unparseable → None
        # (UNVERIFIED); a mangled date never sinks the package.
        return None


# The shipped corpus spells the evidence ledger's columns several ways. The
# canonical general_dma tab reads
#   Evidence_ID · Source · URL · Tier · Recency · Claim_Type · Fact_Count · SubCaps
# while earlier generations used source_name / publish_date / fact_summary /
# subcaps_supported. First alias present wins.
_EV_ALIASES = {
    "source_name": ("source_name", "source", "source_title", "publisher"),
    "source_url": ("url", "source_url", "link"),
    "tier": ("tier", "evidence_tier"),
    "ers": ("ers_score", "ers"),
    "published": ("publish_date", "published_date", "published", "date"),
    # A separate column, and a different KIND of value: "Recency" states a
    # band word (CURRENT / RECENT / …), never a date. Kept apart so a band is
    # never parsed as a date nor a date mistaken for a band.
    "recency": ("recency", "recency_band"),
    "claim_type": ("claim_type", "claim"),
    "fact_count": ("fact_count", "facts"),
    "subcaps": ("subcaps_supported", "subcaps", "subcap_ids"),
    # Only some generations carry the verbatim text here; where they do not,
    # it is mined out of the scoring tabs' Rationale column (see below).
    "excerpt": ("fact_summary", "excerpt", "verbatim", "quote", "summary"),
}

# The excerpt tag the scoring rationales use: "[E-012:F1] Board committees: …"
# — one fact of one evidence item, verbatim, and the only place in the
# general_dma workbook the excerpt text exists at all.
_FACT_TAG = re.compile(r"\[(E-\d+)(?::(F\d+))?\]\s*")


def _stated_band(recency, published) -> str | None:
    """The band word the workbook asserted, carried for the record only.

    The database generates recency_band from a date, and undated evidence is
    UNVERIFIED, never current (charter invariant 9) — so a package that says
    "CURRENT" without a publication date does not get to say it. The claim is
    kept so the disagreement is visible rather than lost."""
    for cand in (recency, published):
        if cand is None or str(cand).strip() == "":
            continue
        if parse_fuzzy_date(cand) is not None:
            continue                    # a real date, not a band word
        return str(cand).strip().upper()
    return None


def _pick(headers: dict, names) -> int | None:
    for n in names:
        if n in headers:
            return headers[n]
    return None


# The ledger tab, under every name the corpus gives it. Measured: of the 153
# packages carrying a workbook, 15 have no `Evidence_Master` at all — eleven
# of those name the same tab `Evidence_Index`, `Evidence_Linkage_Matrix`,
# `Evidence_Linkage`, `Evidence_Detail` or `Evidence_Register`, and reading
# only the one spelling left every one of them with no evidence rows and a
# NULL linked-evidence counter instead of a computed zero.
_EV_TABS = ("Evidence_Master", "Evidence_Index", "Evidence_Register",
            "Evidence_Ledger", "Evidence_Detail", "Evidence_Linkage_Matrix",
            "Evidence_Linkage", "Evidence_Inventory")
_EV_ID_ANCHORS = ("Evidence_ID", "E_ID", "Evidence Id", "EvidenceID", "ID")


def parse_evidence_master(path: str, obs: list | None = None) -> list:
    def observe(kind, detail):
        if obs is not None:
            obs.append(Observation(kind, None, detail))

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        tab = next((t for t in _EV_TABS if t in wb.sheetnames), None)
        if tab is None:
            observe("evidence_ledger_tab_not_found",
                    {"expected_any_of": list(_EV_TABS),
                     "tabs_present": list(wb.sheetnames)[:30],
                     "reason": "no evidence ledger tab: this package lands "
                               "with no evidence rows at all"})
            return []
        ws = wb[tab]
        headers = first = None
        for anchor in _EV_ID_ANCHORS:
            try:
                headers, first = _header_map(ws, anchor)
                break
            except ValueError:
                continue
        if headers is None:
            # No recognisable ledger: the package lands without its
            # evidence tab (links absent, counts computed zero) rather
            # than failing wholesale — but never without saying so.
            observe("evidence_ledger_header_not_found",
                    {"tab": tab, "expected_any_of": list(_EV_ID_ANCHORS),
                     "reason": "the ledger tab exists and its id column could "
                               "not be located; no evidence row was read"})
            return []
        cols = {k: _pick(headers, names) for k, names in _EV_ALIASES.items()}
        cols["e_id"] = _pick(headers, ("evidence_id", "e_id", "id", "evidenceid"))
        out = []
        rows_seen = 0
        for row in ws.iter_rows(min_row=first, values_only=True):
            def v(key):
                i = cols.get(key)
                return row[i] if i is not None and i < len(row) else None
            e_id = str(v("e_id") or "").strip()
            if e_id:
                rows_seen += 1
            if not (e_id.startswith("E-") or e_id.startswith("INT-")):
                continue
            tier = str(v("tier") or "").strip().upper()
            ers = _decimal(v("ers"))
            claim = str(v("claim_type") or "").strip().upper() or None
            facts = _decimal(v("fact_count"))
            out.append({
                "e_id": e_id,
                "source_name": (str(v("source_name")).strip()
                                if v("source_name") else None),
                "source_url": (str(v("source_url")).strip()
                               if v("source_url") else None),
                "tier": tier if tier in ("T1", "T2", "T3", "T4", "T5") else None,
                "ers": None if ers in (None, "UNPARSEABLE") else ers,
                # "Recency" ships a BAND word ("CURRENT"), not a date. A band
                # asserted without a date cannot be honoured: undated evidence
                # is UNVERIFIED, never current (charter invariant 9), so the
                # stated word is carried for the record and the date stays null.
                "published_date": parse_fuzzy_date(v("published")),
                "stated_recency": _stated_band(v("recency"), v("published")),
                "claim_type": claim if claim in
                              ("FACT", "INFERENCE", "HYPOTHESIS",
                               "CEILING_ESTIMATE") else None,
                "fact_count": None if facts in (None, "UNPARSEABLE") else int(facts),
                "excerpt": (str(v("excerpt")).strip() if v("excerpt")
                            and not str(v("excerpt")).strip().isdigit() else None),
                "subcaps": [s for s in
                            (x.strip() for x in str(v("subcaps") or "").split(","))
                            if SUBCAP_RE.match(s)],
            })
        if rows_seen and not out:
            observe("evidence_ledger_ids_unrecognised", {
                "tab": tab, "rows_seen": rows_seen,
                "expected": "E-… or INT-…-…",
                "reason": "the ledger has rows and not one id was in a form "
                          "this parser recognises; no evidence was read"})
        return out
    finally:
        wb.close()


# A fact-grain citation and the header the research workbook puts in front of
# an excerpt block: "[ERS: 4.20] [FACT] [E-012:F1] Source (T2, CURRENT): text".
#
# The fact suffix is OPTIONAL. One research generation writes "[E-012:F1]"
# per fact; another writes a bare "[E-008]" per item. The mandatory-suffix
# version of this expression read the second generation's 709 populated
# Evidence_Excerpt cells and produced zero fragments and zero observations
# — so 127 evidence rows landed excerpt-less, 517 cells had nothing citable
# behind them, and the run's producer was blamed for a package the parser
# had silently half-read. Measured on the Odlum Brown research workbook,
# 2026-08-09: 0 of 709 cells parsed before, 709 of 709 after.
_RW_FACT_RE = re.compile(r"\[(E-\d+)(?::(F\d+))?\]\s*")
# Ledger markup EMBEDDED in a passage — "[E-051 (T2, CURRENT): corroborates.]",
# "[CEILING: L2 …]", "[ERS: 4.0]" — is the researcher annotating, not the
# document speaking. A fragment is cut at the first such annotation: 75 of 78
# excerpts on one package carried this markup INSIDE what rendered as a
# quotation (MEM-0034), and an annotation a reader mistakes for source text
# is worse than a shorter excerpt.
_RW_ANNOTATION_RE = re.compile(
    r"\s*\[(?:E-\d+[^\]]*|CEILING\b[^\]]*|ERS\b[^\]]*|FACT\b|INFERENCE\b|"
    r"HYPOTHESIS\b|CEILING_ESTIMATE\b|T[1-5]\b[^\]]*)\]")
_RW_HEAD_RE = re.compile(r"^\s*\[ERS:\s*([\d.]+)\]\s*(?:\[([A-Z_]+)\]\s*)?")
_RW_SRC_PREFIX_RE = re.compile(r"^[^:]{0,120}?\((T[1-5]),\s*[A-Z_]+\):\s*")
# The research workbook's per-subcap tabs, under every naming convention the
# corpus uses — `P1_Scoring_Detail` in 50 workbooks, `P1_Subcap_Scoring` in 10,
# a bare `P1` in 13. Pinned to the first spelling, 85 of the 135 research
# workbooks in the intake tree yielded nothing at all: no ledger, no fact-grain
# links, no verbatim passages, no absence register, and no word about it.
def _rw_detail_tabs(sheetnames):
    return [t for t in sheetnames if _is_pillar_tab(t)]


def _rw_split_excerpt(blob) -> dict:
    """{fact_id: verbatim text} out of one Evidence_Excerpt cell.

    Each fact's passage runs to the next fact tag. The first passage carries
    the source and tier as a prefix ("BCU 2024 Annual Report (PDF) (T2,
    CURRENT): …") which is provenance, not the quotation, so it is stripped —
    an excerpt has to be what the document says, byte for byte.
    """
    if not blob:
        return {}
    text = _RW_HEAD_RE.sub("", str(blob).strip())
    hits = list(_RW_FACT_RE.finditer(text))
    out = {}
    for n, m in enumerate(hits):
        end = hits[n + 1].start() if n + 1 < len(hits) else len(text)
        # A bare "[E-008]" cell may repeat its own "[ERS: …] [FACT]" header
        # before each subsequent block; strip it wherever a block starts.
        frag = _RW_HEAD_RE.sub("", text[m.end():end].strip())
        frag = _RW_SRC_PREFIX_RE.sub("", frag).strip(" ;·")
        # …and the passage ends where the researcher starts annotating.
        cut = _RW_ANNOTATION_RE.search(frag)
        if cut:
            frag = frag[:cut.start()].strip(" ;·")
        if frag:
            # A bare item id gets F1: the consumer keys the drawer by the
            # e_id half, and an unnumbered fact is still that item's fact.
            out[f"{m.group(1)}:{m.group(2) or 'F1'}"] = frag
    return out


def parse_research_workbook(path: str, obs: list | None = None) -> dict:
    """The research workbook — the evidence tier's real authority.

    The scoring workbook's Evidence_Master carries a Fact_Count but no ERS,
    no publication date and no fact text, which is why every ingested item
    reached the drawer undated, unranked and with an excerpt scraped out of a
    rationale. This tab set carries all three, plus the per-subcap linkage at
    FACT grain and the register of searches that found nothing.

    It never supplies a score: `03_scoring_workbook` is the only authority for
    a score, and this workbook's Score columns are deliberately ignored.

    → {ledger, links, caps, absent} where `ledger` items match
    parse_evidence_master's shape so the two merge on e_id.
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        out = {"ledger": [], "links": [], "caps": [], "absent": []}

        def tab(name, id_col):
            if name not in wb.sheetnames:
                return None, None, None
            ws = wb[name]
            try:
                headers, first = _header_map(ws, id_col)
            except ValueError:
                return None, None, None
            return ws, headers, first

        # ── the ledger: ERS, dates, fact counts, claim classes ────────────
        ws = headers = first = None
        # Linkage matrix first: it is the research generation's own ledger and
        # the only one carrying ERS and a publication date per item.
        for name in ("Evidence_Linkage_Matrix",) + _EV_TABS:
            for anchor in _EV_ID_ANCHORS:
                ws, headers, first = tab(name, anchor)
                if headers is not None:
                    break
            if headers is not None:
                break
        if headers is not None:
            for row in ws.iter_rows(min_row=first, values_only=True):
                def v(*keys, _row=row):
                    for k in keys:
                        i = headers.get(k)
                        if i is not None and i < len(_row) and _row[i] is not None:
                            return _row[i]
                    return None
                e_id = str(v("evidence_id", "e_id") or "").strip()
                if not e_id.startswith("E-"):
                    continue
                tier = str(v("tier") or "").strip().upper()
                ers = _decimal(v("ers_total", "ers", "ers_score"))
                facts = _decimal(v("fact_count", "facts"))
                claim = str(v("claim_types", "claim_type") or "").split(",")[0].strip().upper()
                out["ledger"].append({
                    "e_id": e_id,
                    "source_name": (str(v("source_name")).strip() if v("source_name") else None),
                    "source_url": (str(v("source_url", "url")).strip() if v("source_url", "url") else None),
                    "tier": tier if tier in ("T1", "T2", "T3", "T4", "T5") else None,
                    "ers": None if ers in (None, "UNPARSEABLE") else ers,
                    "published_date": parse_fuzzy_date(v("date_published", "published")),
                    "stated_recency": _stated_band(v("recency"),
                                                   v("date_published", "published")),
                    "claim_type": claim if claim in ("FACT", "INFERENCE", "HYPOTHESIS",
                                                     "CEILING_ESTIMATE") else None,
                    "fact_count": None if facts in (None, "UNPARSEABLE") else int(facts),
                    "excerpt": None,       # filled from the detail tabs below
                    "subcaps": [s for s in
                                (x.strip() for x in
                                 re.split(r"[,;]", str(v("subcap_mappings", "subcaps") or "")))
                                if SUBCAP_RE.match(s)],
                    "signal_direction": (str(v("signal_direction")).strip().upper()
                                         if v("signal_direction") else None),
                })

        # ── per-subcap linkage at fact grain, with its verbatim passages ──
        for name in _rw_detail_tabs(wb.sheetnames):
            ws = headers = first = None
            for anchor in ("SubCap_ID", "Sub_Cap_ID", "SubCapability_ID"):
                ws, headers, first = tab(name, anchor)
                if headers is not None:
                    break
            if headers is None:
                continue
            for row in ws.iter_rows(min_row=first, values_only=True):
                def v(*keys, _row=row):
                    for k in keys:
                        i = headers.get(k)
                        if i is not None and i < len(_row) and _row[i] is not None:
                            return _row[i]
                    return None
                sid = str(v("subcap_id") or "").strip()
                if not SUBCAP_RE.match(sid):
                    continue
                facts = [f.strip() for f in
                         re.split(r"[,;]", str(v("evidence_ids") or "")) if f.strip()]
                out["links"].append({
                    "subcap_id": sid,
                    # fact ids kept whole — "E-012:F1" is finer than "E-012"
                    # and the drawer can say which fact carried the claim
                    "fact_ids": [f for f in facts if f.upper().startswith("E-")],
                    "e_ids": sorted({f.split(":")[0] for f in facts
                                     if f.upper().startswith("E-")}),
                    "excerpts": _rw_split_excerpt(v("evidence_excerpt")),
                    "_had_excerpt_cell": bool(str(v("evidence_excerpt") or "").strip()),
                    "source_document": (str(v("source_document")).strip()
                                        if v("source_document") else None),
                    "urls": [u.strip() for u in
                             re.split(r"[,;\s]+", str(v("evidence_urls") or ""))
                             if u.strip().startswith("http")],
                    "evidence_tier": (str(v("evidence_tier")).strip().upper()
                                      if v("evidence_tier") else None),
                    "diagnostic_question": (str(v("diagnostic_question")).strip()
                                            if v("diagnostic_question") else None),
                    "caps_applied": (str(v("caps_applied")).strip()
                                     if v("caps_applied") else None),
                })

        # ── the caps log and the absence register ─────────────────────────
        # The caps log states which cells a safeguard held down and why. Its
        # id column is spelled four ways across the corpus and its score
        # columns five, so a single-spelling read returned zero caps from
        # 1,457 populated rows — an assessment whose safeguards left no trace.
        ws = headers = first = None
        for anchor in ("SubCap_ID", "Sub_Cap_ID", "SubCaps_Affected",
                       "Subcap_IDs"):
            ws, headers, first = tab("Caps_Applied_Log", anchor)
            if headers is not None:
                break
        if headers is not None:
            caps_rows = 0
            for row in ws.iter_rows(min_row=first, values_only=True):
                def v(*keys, _row=row):
                    for k in keys:
                        i = headers.get(k)
                        if i is not None and i < len(_row) and _row[i] is not None:
                            return _row[i]
                    return None
                raw = str(v("subcap_id", "sub_cap_id", "subcaps_affected",
                            "subcap_ids") or "").strip()
                if not raw:
                    continue
                caps_rows += 1
                # One row may name several cells ("P1C1.1, P1C1.2"); a cap is
                # an assertion about each of them.
                for sid in (x.strip() for x in re.split(r"[,;]", raw)):
                    if not SUBCAP_RE.match(sid):
                        continue
                    out["caps"].append({
                        "subcap_id": sid,
                        "cap_type": (str(v("cap_type")).strip() if v("cap_type") else None),
                        "cap_reason": (str(v("cap_reason", "cap_rule", "rationale",
                                             "trigger", "reason")).strip()
                                       if v("cap_reason", "cap_rule", "rationale",
                                            "trigger", "reason") else None),
                        "pre_cap_score": _num(v("pre_cap_score", "prior_score",
                                                "original_score", "score_before")),
                        "post_cap_score": _num(v("post_cap_score", "capped_score",
                                                 "cap_value", "max_score",
                                                 "ceiling", "cap_ceiling",
                                                 "score_after")),
                        "e_id": (str(v("evidence_id", "e_id", "evidence_ids",
                                       "evidence_refs")).strip()
                                 if v("evidence_id", "e_id", "evidence_ids",
                                      "evidence_refs") else None),
                    })
            if caps_rows and not out["caps"] and obs is not None:
                obs.append(Observation("caps_log_ids_unrecognised", None, {
                    "tab": "Caps_Applied_Log", "rows_seen": caps_rows,
                    "expected": SUBCAP_RE.pattern,
                    "reason": "the caps log has rows and none names a cell "
                              "this parser recognises; no cap was read"}))

        # This is the absence protocol's own ladder, already run by the
        # assessment: which cells were searched, how hard, and what the
        # highest tier reached was. Emitting a thin alert without it is
        # emitting an absence with no recorded search.
        ws, headers, first = tab("Absent_Evidence_Log", "SubCap_ID")
        if headers is not None:
            for row in ws.iter_rows(min_row=first, values_only=True):
                def v(*keys, _row=row):
                    for k in keys:
                        i = headers.get(k)
                        if i is not None and i < len(_row) and _row[i] is not None:
                            return _row[i]
                    return None
                sid = str(v("subcap_id") or "").strip()
                if not sid or not sid.upper().startswith("P"):
                    continue
                out["absent"].append({
                    "subcap_id": sid,
                    "name": (str(v("subcapability")).strip() if v("subcapability") else None),
                    "diagnostic_question": (str(v("diagnostic_question")).strip()
                                            if v("diagnostic_question") else None),
                    "search_count": (str(v("search_count")).strip() if v("search_count") else None),
                    "tiers_searched": (str(v("tiers_searched")).strip() if v("tiers_searched") else None),
                    "highest_tier_found": (str(v("highest_tier_found")).strip()
                                           if v("highest_tier_found") else None),
                    "reason": (str(v("reason")).strip() if v("reason") else None),
                    "discovery_question": (str(v("discovery_question")).strip()
                                           if v("discovery_question") else None),
                    "impact_note": (str(v("impact_note")).strip() if v("impact_note") else None),
                })

        # Hoist the best passage per evidence item onto the ledger: the
        # drawer cites an ITEM, so it needs one verbatim excerpt, and the
        # longest passage is the one that carries the claim rather than a
        # fragment of it. Floor of 50 chars is the contract's.
        best: dict = {}
        cells_with_text = sum(1 for l in out["links"] if l.get("_had_excerpt_cell"))
        for link in out["links"]:
            link.pop("_had_excerpt_cell", None)
            for fact_id, text in link["excerpts"].items():
                e_id = fact_id.split(":")[0]
                if len(text) >= 50 and len(text) > len(best.get(e_id, "")):
                    best[e_id] = text
        for item in out["ledger"]:
            if best.get(item["e_id"]):
                item["excerpt"] = best[item["e_id"]][:500]
        if obs is not None and cells_with_text and not best:
            # REF-0004's rule, applied to the one reader it missed: a reader
            # that does not recognise its input must produce a NAMED
            # observation, never an empty result. This exact silence cost a
            # promoted run its entire citable evidence base — the cells were
            # populated, the expression could not see them, and nothing said
            # so anywhere.
            obs.append(Observation("research_excerpt_format_unrecognised", None, {
                "excerpt_cells_with_text": cells_with_text,
                "fragments_parsed": 0,
                "expected": "[E-nnn:Fn] or [E-nnn] fact tags inside "
                            "Evidence_Excerpt",
                "reason": "the detail tabs carry populated Evidence_Excerpt "
                          "cells and not one parsed into a fragment; every "
                          "ledger row will land excerpt-less and nothing "
                          "downstream will be citable"}))
        if obs is not None and not any(out.values()):
            obs.append(Observation("research_workbook_yielded_nothing", None, {
                "tabs_present": list(wb.sheetnames)[:30],
                "expected_ledger_any_of": ["Evidence_Linkage_Matrix", *_EV_TABS],
                "expected_detail": "a P<n>_* subcapability tab",
                "reason": "the research workbook was read and produced no "
                          "ledger row, no fact-grain link, no cap and no "
                          "recorded absence"}))
        return out
    finally:
        wb.close()


def mine_evidence_from_rationales(scores: list) -> dict:
    """Verbatim excerpts and subcap links, mined out of the scoring rationales.

    The general_dma Evidence_Master carries a Fact_Count but no fact TEXT, so
    without this every ingested evidence row reaches the evidence drawer with
    an empty excerpt — and an evidence drawer with no excerpt is the one thing
    the product cannot ship (invariant 4 requires a verbatim excerpt of
    50–500 chars behind every citation).

    The text does exist: each subcap's Rationale opens with tagged fragments,
    `[E-012:F1] Board committees: Technology Committee (…)`, one per cited
    fact. Returns `{e_id: {"excerpt": longest fragment, "fragments": [...],
    "subcaps": [ids that cite it]}}`.

    Nothing is composed or paraphrased here — a fragment is stored exactly as
    the assessor wrote it, and the longest is chosen only because the excerpt
    column holds one.
    """
    out: dict = {}
    for s in scores or []:
        text = str(getattr(s, "rationale", "") or "")
        for e_id in getattr(s, "evidence_refs", None) or []:
            rec = out.setdefault(str(e_id), {"fragments": [], "subcaps": []})
            if s.subcap_id not in rec["subcaps"]:
                rec["subcaps"].append(s.subcap_id)
        if not text:
            continue
        # Split on the tags, keeping each tag with the text that follows it.
        marks = list(_FACT_TAG.finditer(text))
        for i, m in enumerate(marks):
            e_id = m.group(1)
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            frag = text[m.end():end]
            # A fragment ends at the next evidence tag OR at the next section
            # label ([MATURITY]: / [GAP]: / [CEILING]: / [SO WHAT]: …), whichever
            # comes first. Without the second cut, one fact's excerpt swallows
            # the assessor's maturity reasoning and stops being verbatim.
            cut = re.search(r"\[[A-Z][A-Z ]{2,}\]\s*:?", frag)
            if cut:
                frag = frag[:cut.start()]
            frag = frag.strip().strip(" .;·")
            # 50, not 20. A citation needs a 50-500 character span: that is
            # what the column comment states, what `register_evidence`
            # refuses outside, and what ET-04 blocks a citation for. A mined
            # 20-49 character fragment used to land, link to cells, and then
            # refuse the first producer who tried to cite it — so the miner
            # was manufacturing a defect that surfaced two stages later,
            # wearing the appearance of evidence the whole way.
            if len(frag) < 50:
                continue
            rec = out.setdefault(e_id, {"fragments": [], "subcaps": []})
            if frag not in rec["fragments"]:
                rec["fragments"].append(frag)
            if s.subcap_id not in rec["subcaps"]:
                rec["subcaps"].append(s.subcap_id)
    for e_id, rec in out.items():
        best = max(rec["fragments"], key=len) if rec["fragments"] else None
        # The column is bounded at 500 chars by the registration gate; a
        # longer fragment is truncated on a word boundary rather than dropped.
        if best and len(best) > 500:
            best = best[:500].rsplit(" ", 1)[0]
        rec["excerpt"] = best
    return out


# Pillar-grain scoring tabs, across every shipped naming convention seen in
# the corpus: P1_Subcap_Scoring · P1_Scoring_Detail · P1_Scoring · P1 ·
# P1_RIAs_Broker_Dealers. Anything starting with a pillar token is a
# candidate; these suffixes mark the tabs that are rollups, logs or
# metadata rather than subcapability rows.
_NOT_SCORING = ("rollup", "summary", "benchmark", "peer", "log", "chain",
                "metadata", "caps", "issue", "priority", "index", "check",
                "contradiction", "validation", "absent", "linkage", "revision",
                "recommendation", "weight", "taxonomy", "estimate")


def _is_pillar_tab(tab: str) -> bool:
    if not re.match(r"^P\d+($|[_ ])", tab):
        return False
    low = tab.lower()
    return not any(x in low for x in _NOT_SCORING)


_CATEGORY_RE = re.compile(r"^P\d+C\d+$")
_PILLAR_RE = re.compile(r"^P\d+$")

# The same category id, as the peer tabs actually label their rows:
# `P1C1`, `P1C1: Digital Strategy & Roadmap`, `P1C1_digital_strategy`. The
# lookahead keeps a SUBCAP id (`P1C1.1`) out — that is a different grain.
_CATEGORY_LABEL_RE = re.compile(r"^(P\d+C\d+)(?=$|[^0-9.])")


def _category_id(value) -> str | None:
    m = _CATEGORY_LABEL_RE.match(str(value or "").strip())
    return m.group(1) if m else None

# Peer_Benchmarks stat columns, under every header spelling the corpus uses.
# Anything NOT in here is a named peer institution, so a missing alias does
# not degrade gracefully — it invents a peer. Keyed by _norm() output.
_STAT_ALIASES = {
    "category": "category", "category_id": "category", "cat": "category",
    "category_name": "category_name", "name": "category_name",
    "entity_score": "entity_score", "entity": "entity_score",
    "score": "entity_score", "our_score": "entity_score",
    "peer_median": "median", "median": "median", "cohort_median": "median",
    "peer_p25": "p25", "p25": "p25", "q1": "p25", "percentile_25": "p25",
    "peer_p75": "p75", "p75": "p75", "q3": "p75", "percentile_75": "p75",
    "peer_min": "min", "min": "min", "peer_max": "max", "max": "max",
    "delta_vs_median": "delta", "delta": "delta", "vs_median": "delta",
    "gap": "delta", "priority": "priority", "subcap_count": "subcap_count",
    "pillar": "pillar", "level": "level", "confidence": "confidence",
}


# Stat headers the corpus writes freely rather than from a fixed list:
# `Gap_vs_Median`, `Gap_to_Median`, `vs_Peer`, `Position`, `Cat_ID`,
# `Peer_Name`, `Unknown`, `Percentile_Rank`, … Measured across the corpus,
# 28 clients had at least one of these read as a named peer institution.
_STAT_PATTERNS = (
    # NOT a bare `delta*`: `Delta_Community` is a real credit union, and a
    # name-only rule that swallowed it would drop a peer instead of inventing
    # one — the same defect facing the other way.
    (re.compile(r"^(gap|diff|variance)(_|$)"), "delta"),
    (re.compile(r"^delta_(vs|to|from|median|peer)"), "delta"),
    (re.compile(r"^vs_"), "delta"),
    (re.compile(r"_vs_"), "delta"),
    (re.compile(r"^(position|rank|ranking|quartile|percentile\w*)$"), "priority"),
    (re.compile(r"^(cat|cat_id|category\w*)$"), "category"),
    (re.compile(r"^(peer_name|peer|peers|institution|entity_name|unknown|"
                r"n_a|na|blank|notes?|comments?|status|source|basis|cohort|"
                r"method\w*)$"), "note"),
)


def _stat_key(header: str):
    """The canonical stat a header names, or None when it names a peer."""
    n = _norm(header)
    hit = _STAT_ALIASES.get(n)
    if hit:
        return hit
    for pattern, canonical in _STAT_PATTERNS:
        if pattern.search(n):
            return canonical
    return None


#: Tab spellings for the two stated grains. One literal name was read until
#: 2026-08-18 and a workbook that spells it any other way lost both grains in
#: silence. Matched case- and separator-insensitively, so `Pillar Summary`,
#: `pillar_summary` and `PillarSummary` are one name.
_GRAIN_TABS = {
    "pillars": ("Pillar_Summary", "Pillar Summary", "Pillar_Scores",
                "Pillar Scores", "Pillar_Rollup", "Pillar Rollup",
                "Pillar_Detail", "1_Pillar_Summary", "Summary_Pillar"),
    "categories": ("Category_Detail", "Category Detail", "Category_Scores",
                   "Category Scores", "Category_Scorecard",
                   "Category Scorecard", "Category_Summary",
                   "Category Summary", "Category_Rollup", "2_Category_Detail"),
}
#: The header cell each grain's table is anchored on, in preference order.
_GRAIN_ANCHORS = {
    "pillars": ("Pillar", "Pillar_ID", "Pillar ID"),
    "categories": ("Category_ID", "Category ID", "Category"),
}


def _tab_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").lower())


def parse_grain_summaries(path: str, observations: list | None = None) -> dict:
    """The workbook's own STATED pillar and category grains
    (Pillar_Summary / Category_Detail tabs, cached formula values). H4's
    grain lock forbids recomputing these by averaging subcaps — cap
    logic, weighting and analyst override are applied when they are
    struck. The rubric Level column (M1-M5) is deliberately not read:
    display banding is the app's four-band rule over raw scores.

    THE SILENCE THIS CLOSES, measured 2026-08-18 on the third client.
    Every other companion parser here takes the `observations` list and
    appends what it could not read; this one was the exception, and it had
    three distinct ways to return nothing — tab absent, header row not
    locatable, no Score column — all spelled `(None, None, None)` and none
    of them recorded. The client's run landed with `pillars: 0,
    categories: 0` against the reference client's 4 and 17, its bundle note
    still saying both grains are stated with source cells, and no row
    anywhere naming what had happened. Downstream: the workbook zoom served
    an empty state at both grains, the overview pillar bars had to derive
    means the workbook already stated, and no peer median existed at any
    grain to compare against. One unrecognised tab name, four surfaces.

    The observation is the fix that matters more than the aliases: a
    spelling nobody has met yet still loses the grains, and now it says so
    by name instead of looking like a workbook that states none.
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = {"pillars": [], "categories": []}
    obs = observations if observations is not None else []
    present = {_tab_key(n): n for n in wb.sheetnames}

    def _tab_headers(grain: str):
        """The tab for this grain, or nothing plus the reason why nothing.

        Each branch names a DIFFERENT next move for whoever reads the
        observation: add a spelling, fix the header row, or find the score
        column. "no stated grains" means all three and therefore none.
        """
        name = next((present[_tab_key(c)] for c in _GRAIN_TABS[grain]
                     if _tab_key(c) in present), None)
        if name is None:
            obs.append(Observation(
                "grain_tab_not_found", None,
                {"grain": grain, "tried": list(_GRAIN_TABS[grain]),
                 "tabs": list(wb.sheetnames)[:30],
                 "consequence": (
                     f"no stated {grain} grain lands for this run. The "
                     "workbook zoom serves an empty state at this grain and "
                     "no peer median exists to compare against; add the "
                     "tab's spelling to _GRAIN_TABS rather than letting the "
                     "run look like a workbook that states none")}))
            return None, None, None
        ws = wb[name]
        for anchor in _GRAIN_ANCHORS[grain]:
            try:
                headers, first = _header_map(ws, anchor)
                break
            except ValueError:
                continue
        else:
            obs.append(Observation(
                "grain_header_not_found", None,
                {"grain": grain, "tab": name,
                 "anchors_tried": list(_GRAIN_ANCHORS[grain])}))
            return None, None, None
        if "score" not in headers:
            obs.append(_column_not_found(name, "score", ("score",), headers))
            return None, None, None
        return ws, headers, first

    try:
        ws, headers, first = _tab_headers("pillars")
        if headers is not None:
            for r, row in enumerate(ws.iter_rows(min_row=first, values_only=True), first):
                def v(*keys, _row=row):
                    # first alias that resolves: the corpus spells these
                    # headers several ways and a single-alias lookup silently
                    # nulls the column (Pillar_Summary.Weight was read only
                    # as `weight_ib`, so every pillar weight was null)
                    for key in keys:
                        i = headers.get(key)
                        if i is not None and i < len(_row) and _row[i] is not None:
                            return _row[i]
                    return None
                pid = str(v("pillar", "pillar_id") or "").strip()
                if not _PILLAR_RE.match(pid):
                    continue
                score_col = openpyxl.utils.get_column_letter(headers["score"] + 1)
                out["pillars"].append({
                    "pillar_id": pid,
                    "name": (str(v("pillar_name")).strip() if v("pillar_name") else None),
                    "score": _num(v("score")),
                    "weight": _num(v("weight_ib", "weight", "weight_pct")),
                    "peer_median": _num(v("peer_median", "median")),
                    "source_cell": f"{ws.title}!{score_col}{r}",
                })
        ws, headers, first = _tab_headers("categories")
        if headers is not None:
            for r, row in enumerate(ws.iter_rows(min_row=first, values_only=True), first):
                def v(*keys, _row=row):
                    for key in keys:
                        i = headers.get(key)
                        if i is not None and i < len(_row) and _row[i] is not None:
                            return _row[i]
                    return None
                cid = str(v("category_id", "category") or "").strip()
                if not _CATEGORY_RE.match(cid):
                    continue
                score_col = openpyxl.utils.get_column_letter(headers["score"] + 1)
                out["categories"].append({
                    "category_id": cid,
                    "name": (str(v("category_name")).strip() if v("category_name") else None),
                    "pillar_id": (str(v("pillar")).strip() if v("pillar") else cid.split("C")[0]),
                    "score": _num(v("score")),
                    "peer_median": _num(v("peer_median", "median")),
                    "priority_score": _num(v("priority_score", "priority")),
                    "priority_tier": (str(v("priority_tier")).strip() if v("priority_tier") else None),
                    "source_cell": f"{ws.title}!{score_col}{r}",
                })
        return out
    finally:
        wb.close()


def _num(value):
    d = _decimal(value)
    return None if d in (None, "UNPARSEABLE") else float(d)


def _peer_header_row(rows: list):
    """Index of the header row, or None. The header is NOT reliably row 1:
    seven packages put a title, a methodology note or a run id above it
    (`Peer Benchmarking — METHODOLOGY NOTE`, `DMA-RES-APGFCU-… | Peer
    Benchmarks | SV2 Credit Union Medium | Maryland`), and reading row 1 as
    the header made every peer column a fragment of that sentence."""
    best, best_hits = None, 0
    for i, row in enumerate(rows[:10]):
        if not row:
            continue
        hits = sum(1 for h in row if h is not None and _stat_key(str(h)))
        named = sum(1 for h in row if h is not None and str(h).strip())
        if hits and named >= 2 and hits > best_hits:
            best, best_hits = i, hits
    return best


def parse_peer_benchmarks(path: str, obs: list | None = None) -> list:
    """Peer_Benchmarks is CATEGORY grain with named-peer columns after the
    stat block. Only the per-peer scores are data — Entity_Score and the
    stat columns (median/quartiles/min/max/delta) are derivable, so they
    are read solely to verify, never to store (counts are computed, never
    stored, where a source of truth exists). Stops at the footer notes.

    A column is a peer only if it BOTH fails to name a known stat and holds
    values on the maturity scale. The name test alone invents institutions:
    28 clients in the corpus carried a peer called `Gap_vs_Median`,
    `Position`, `Peer_Name`, `Cat_ID` or `Unknown`, and every one of those
    would have rendered in the cohort as a bank that does not exist."""
    def observe(kind, detail):
        if obs is not None:
            obs.append(Observation(kind, None, detail))

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if "Peer_Benchmarks" not in wb.sheetnames:
            return []
        ws = wb["Peer_Benchmarks"]
        rows = [r for r in ws.iter_rows(values_only=True) if r]
        if not rows:
            return []
        h = _peer_header_row(rows)
        if h is None:
            observe("peer_header_not_found", {
                "tab": "Peer_Benchmarks",
                "row_1": [str(v)[:60] for v in rows[0] if v is not None][:8],
                "reason": "no row in the first ten named a recognised peer "
                          "statistic; no peer row was read"})
            return []
        header, body = rows[h], rows[h + 1:]
        candidates = [(i, str(x).strip()) for i, x in enumerate(header)
                      if x is not None and _stat_key(str(x)) is None
                      and str(x).strip()]

        def col(canonical, row):
            """The row's value for a canonical stat, under any of its aliases."""
            for i, x in enumerate(header):
                if x is not None and _stat_key(str(x)) == canonical:
                    return row[i] if i < len(row) else None
            return None
        # Non-numeric cells ("N/A", footnotes) are None here — a peer grid
        # is data or nothing, and downstream median verification sorts
        # these values.
        num = (lambda v: None if (d := _decimal(v)) in (None, "UNPARSEABLE") else d)
        graded = [r for r in body if _category_id(r[0])]
        if body and not graded:
            observe("peer_rows_unrecognised", {
                "tab": "Peer_Benchmarks", "rows_seen": len(body),
                "first_column_examples": sorted(
                    {str(r[0]).strip()[:40] for r in body if r and r[0]})[:5],
                "expected": _CATEGORY_LABEL_RE.pattern,
                "reason": "the tab has rows and none is at category grain "
                          "(a peer-per-row layout reads this way); no peer "
                          "score was read"})
            return []

        # The value test. A peer is scored on the same M1–M5 scale as the
        # entity; a column of gaps, ranks or words is a statistic or a label
        # whatever it calls itself, and is refused BY NAME rather than
        # stored as an institution.
        peer_cols, refused, unscored = [], [], []
        for i, name in candidates:
            values = [row[i] for row in graded if i < len(row)]
            populated = [v for v in values if v is not None and str(v).strip()]
            nums = [d for d in (num(v) for v in populated) if d is not None]
            out_of_band = [d for d in nums if not (SCORE_MIN <= d <= SCORE_MAX)]
            if not populated:
                # A peer the tab NAMES but never scores. It is a real
                # institution and it keeps its column; every score is null,
                # which is what the cohort should say about it.
                peer_cols.append((i, name))
                unscored.append(name)
            elif nums and not out_of_band:
                peer_cols.append((i, name))
            else:
                refused.append({
                    "column": name,
                    "values_seen": len(populated),
                    "numeric": len(nums),
                    "outside_rubric": [str(d) for d in out_of_band][:4],
                    "examples": [str(v)[:30] for v in populated][:4]})
        if refused:
            observe("peer_column_unrecognised", {
                "tab": "Peer_Benchmarks", "columns": refused,
                "rubric": f"{SCORE_MIN}–{SCORE_MAX}",
                "reason": "column names no known statistic and does not hold "
                          "scores on the maturity scale; not stored as a peer"})
        if unscored:
            observe("peer_column_unscored", {
                "tab": "Peer_Benchmarks", "columns": sorted(unscored),
                "reason": "named in the cohort and scored in no category; "
                          "kept with null scores, never a computed zero"})

        out = []
        for row in graded:
            cat = _category_id(row[0])
            # The name comes from the column that declares itself a name.
            # Reading row[1] positionally put a peer's SCORE in the name
            # field whenever the tab has no Category_Name column.
            cat_name = col("category_name", row)
            out.append({
                "category_id": cat,
                "category_name": (str(cat_name).strip() or None) if cat_name is not None else None,
                "entity_score": num(col("entity_score", row)),
                "stated_median": num(col("median", row)),
                "peers": [(name, num(row[i]) if i < len(row) else None)
                          for i, name in peer_cols],
            })
        return out
    finally:
        wb.close()


# Column names a Recommendations header row uses. A row is the header when it
# names at least two of them; anything above it is a title, a deferral note or
# a status line, and reading THAT as the header destroyed the tab.
_REC_HEADER_WORDS = {
    "rec_id", "recommendation", "recommendations", "title", "priority", "rank",
    "category", "category_id", "pillar", "theme", "initiative", "owner",
    "effort", "impact", "horizon", "timeline", "phase", "status", "rationale",
    "description", "subcap_id", "capability", "sequence", "value", "outcome",
    "zennify_solution", "solution", "offering", "dependency", "cost",
}


def _rec_header_row(rows: list):
    """Index of the header row, or None when the tab starts straight into
    data (`CI Segal Bryant & Hammill` opens with `1 | FSC/Sales Cloud`)."""
    for i, row in enumerate(rows[:10]):
        if not row:
            continue
        names = {_norm(str(v)) for v in row if v is not None and str(v).strip()}
        if len(names & _REC_HEADER_WORDS) >= 2:
            return i
    return None


def parse_recommendations(path: str, obs: list | None = None) -> list:
    """The Recommendations tab lands raw: rec_id as it arrived (the raw
    tier preserves package identifiers) plus the full row as payload.

    Neither the header row nor the id column can be assumed. Measured across
    the corpus, twenty packages put a title or deferral note above the header
    and 26 lost rows to a de-duplication keyed on the raw first column —
    Amarillo National Bank's 29 recommendations became 0, Cetera's 24 became
    4 — because that column repeats a priority rank or a phase label."""
    def observe(kind, detail):
        if obs is not None:
            obs.append(Observation(kind, None, detail))

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if "Recommendations" not in wb.sheetnames:
            return []
        ws = wb["Recommendations"]
        all_rows = [r for r in ws.iter_rows(values_only=True) if r]
        if not all_rows:
            return []
        h = _rec_header_row(all_rows)
        if h is None:
            observe("recommendations_header_not_found", {
                "tab": "Recommendations",
                "row_1": [str(v)[:60] for v in all_rows[0] if v is not None][:6],
                "expected_any_of": sorted(_REC_HEADER_WORDS)[:12],
                "reason": "no row in the first ten named two recognised "
                          "recommendation columns; columns land positionally"})
            first = ()
            rows = iter(all_rows)
        else:
            first = all_rows[h]
            rows = iter(all_rows[h + 1:])
        header = [(_norm(str(x)) if x is not None else None) for x in first]
        # The first column is a rec id in some packages and a bare priority
        # rank in others (BCU's header is `Priority` with values 1..8).
        # Requiring a REC- prefix dropped every recommendation in those
        # packages silently, which is why the platform page served none.
        # A row is a recommendation when it carries content, and the raw
        # tier keeps whatever identifier arrived — synthesising REC-n from
        # the rank where the package states no id.
        id_is_rank = header and header[0] in ("priority", "rank", "order", "no", "num")
        out = []
        seen = set()
        collided = 0
        content_rows = 0
        for n, row in enumerate(rows, 1):
            if not row:   # read-only mode yields () for blank rows
                continue
            raw = str(row[0] or "").strip()
            if not raw:
                continue
            payload = {header[i]: (str(row[i]).strip() if i < len(row) and row[i] is not None else None)
                       for i in range(len(header)) if header[i]}
            if not payload:      # no usable header: keep the row positionally
                payload = {f"col_{i + 1}": (str(v).strip() if v is not None else None)
                           for i, v in enumerate(row)}
            # a row whose only populated cell is the id is a footer or spacer
            if not any(v for k, v in payload.items()
                       if k != (header[0] if header else "col_1")):
                continue
            content_rows += 1
            rec_id = f"REC-{raw}" if id_is_rank or not raw.upper().startswith("REC-") else raw
            if rec_id in seen:
                # The id repeats; the ROW does not. Dropping it here is how
                # 26 packages lost recommendations the tab plainly listed —
                # the raw tier keeps every stated row, and an id that cannot
                # be unique is qualified by its position instead of deciding
                # which recommendation the client does not get to read.
                collided += 1
                rec_id = f"{rec_id}#{n}"
            if rec_id in seen:
                continue
            seen.add(rec_id)
            out.append({"rec_id": rec_id, "payload": payload})
        if collided:
            observe("recommendation_id_not_unique", {
                "tab": "Recommendations", "id_column": (header[0] if header else None),
                "rows_qualified_by_position": collided,
                "rows_kept": len(out), "content_rows": content_rows,
                "reason": "the first column repeats, so it is not an id; rows "
                          "are kept under a position-qualified id rather than "
                          "de-duplicated away"})
        if content_rows and not out:
            observe("recommendations_all_dropped", {
                "tab": "Recommendations", "content_rows": content_rows,
                "reason": "the tab has populated rows and none survived "
                          "parsing"})
        return out
    finally:
        wb.close()
