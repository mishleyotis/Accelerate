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
EID_RE = re.compile(r"\bE-[A-Z]{0,3}\d{2,4}(?::F\d+)?\b")


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


@dataclass
class Observation:
    kind: str          # missing_score · unparseable_cell
    subcap_id: str
    detail: dict


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
        pillar_tabs = [t for t in wb.sheetnames if re.match(r"P\d+_Subcap_Scoring$", t)]
        if pillar_tabs:
            return _parse_pillar_scoring(wb, pillar_tabs)
        raise ValueError(f"unrecognised scoring workbook generation: tabs={wb.sheetnames}")
    finally:
        wb.close()


CONFIDENCE_WORDS = {"HIGH", "MEDIUM", "LOW"}


def _parse_pillar_scoring(wb, pillar_tabs) -> WorkbookParse:
    result = WorkbookParse(scores=[], observations=[], toggled_out=[])
    for tab in sorted(pillar_tabs):
        ws = wb[tab]
        headers, first = _header_map(ws, "SubCap_ID")
        sid_col = headers["subcap_id"]
        score_col = headers["score"]
        score_letter = openpyxl.utils.get_column_letter(score_col + 1)
        conf_col = headers.get("confidence")
        name_col = headers.get("subcap_name")
        eids_col = headers.get("evidence_ids")
        rationale_col = headers.get("rationale")
        for r, row in enumerate(ws.iter_rows(min_row=first, values_only=True), first):
            sid = row[sid_col] if sid_col < len(row) else None
            sid = str(sid).strip() if sid else None
            if not sid or not SUBCAP_RE.match(sid):
                continue
            pillar, category, capability = _grain(sid)
            score = _decimal(row[score_col] if score_col < len(row) else None)
            cell = f"{tab}!{score_letter}{r}"
            if score == "UNPARSEABLE":
                result.observations.append(Observation(
                    "unparseable_cell", sid, {"source_cell": cell,
                                              "raw": str(row[score_col])[:80]}))
                continue
            refs_raw = str(row[eids_col]) if eids_col is not None and row[eids_col] else ""
            rationale = str(row[rationale_col]).strip() if rationale_col is not None and row[rationale_col] else None
            if score is None:
                if refs_raw.strip() or rationale:
                    result.observations.append(Observation(
                        "missing_score", sid, {"source_cell": cell}))
                else:
                    result.toggled_out.append(sid)
                continue
            conf = None
            if conf_col is not None and row[conf_col] is not None:
                c = str(row[conf_col]).strip().upper()
                conf = c if c in CONFIDENCE_WORDS else None
            result.scores.append(ParsedScore(
                subcap_id=sid, pillar_id=pillar, category_id=category,
                capability_id=capability,
                name=(str(row[name_col]).strip() if name_col is not None and row[name_col] else None),
                tier=None, score=score, source_cell=cell,
                evidence_quality=None, confidence=conf,
                facets=[], evidence_refs=sorted({m.split(":")[0] for m in EID_RE.findall(refs_raw)}),
            ))
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
    year = int(m.group(1))
    if m.group(2):
        q = int(m.group(2))
        month, day = 3 * q, (31, 30, 30, 31)[q - 1]
        return date(year, month, day)
    if m.group(3):
        return date(year, int(m.group(3)), 1)
    return date(year, 1, 1)


def parse_evidence_master(path: str) -> list:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if "Evidence_Master" not in wb.sheetnames:
            return []
        ws = wb["Evidence_Master"]
        headers, first = _header_map(ws, "Evidence_ID")
        out = []
        for row in ws.iter_rows(min_row=first, values_only=True):
            def v(key):
                i = headers.get(key)
                return row[i] if i is not None and i < len(row) else None
            e_id = str(v("evidence_id") or "").strip()
            if not e_id.startswith("E-"):
                continue
            tier = str(v("tier") or "").strip().upper()
            ers = _decimal(v("ers_score"))
            out.append({
                "e_id": e_id,
                "source_name": (str(v("source_name")).strip() if v("source_name") else None),
                "source_url": (str(v("url")).strip() if v("url") else None),
                "tier": tier if tier in ("T1", "T2", "T3", "T4", "T5") else None,
                "ers": None if ers in (None, "UNPARSEABLE") else ers,
                "published_date": parse_fuzzy_date(v("publish_date")),
                "excerpt": (str(v("fact_summary")).strip() if v("fact_summary") else None),
                "subcaps": [s for s in
                            (x.strip() for x in str(v("subcaps_supported") or "").split(","))
                            if SUBCAP_RE.match(s)],
            })
        return out
    finally:
        wb.close()
