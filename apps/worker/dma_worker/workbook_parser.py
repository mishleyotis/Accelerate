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
    rationale: str | None = None       # scorer's grounding text; embedded, never stored


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
        pillar_tabs = [t for t in wb.sheetnames if _is_pillar_tab(t)]
        if pillar_tabs:
            return _parse_pillar_scoring(wb, pillar_tabs)
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
        raise ValueError(f"unrecognised scoring workbook generation: tabs={wb.sheetnames}")
    finally:
        wb.close()


CONFIDENCE_WORDS = {"HIGH", "MEDIUM", "LOW"}


# Score-column names across the shipped variants, in preference order —
# post-critic beats pre-critic where a critic pass shipped both.
_SCORE_KEYS = ("score", "post_critic_score", "score_1_to_5",
               "effective_score", "final_score")
_NAME_KEYS = ("subcap_name", "subcapability", "sub_cap_name")


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
        eids_col = headers.get("evidence_ids")
        rationale_col = headers.get("rationale")
        if rationale_col is None:  # e.g. "Rationale (≥150 chars)"
            rationale_col = next((v for k, v in headers.items()
                                  if k.startswith("rationale")), None)
        for r, row in enumerate(ws.iter_rows(min_row=first, values_only=True), first):
            def cell_at(i, _row=row):
                return _row[i] if i is not None and i < len(_row) else None
            sid = cell_at(sid_col)
            sid = str(sid).strip() if sid else None
            if not sid or not SUBCAP_RE.match(sid):
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


def parse_evidence_master(path: str) -> list:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if "Evidence_Master" not in wb.sheetnames:
            return []
        ws = wb["Evidence_Master"]
        try:
            headers, first = _header_map(ws, "Evidence_ID")
        except ValueError:
            # Some corpus variants label the id column differently.
            try:
                headers, first = _header_map(ws, "E_ID")
            except ValueError:
                # No recognisable ledger: the package lands without its
                # evidence tab (links absent, counts computed zero) rather
                # than failing wholesale.
                return []
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


def parse_grain_summaries(path: str) -> dict:
    """The workbook's own STATED pillar and category grains
    (Pillar_Summary / Category_Detail tabs, cached formula values). H4's
    grain lock forbids recomputing these by averaging subcaps — cap
    logic, weighting and analyst override are applied when they are
    struck. The rubric Level column (M1-M5) is deliberately not read:
    display banding is the app's four-band rule over raw scores."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = {"pillars": [], "categories": []}

    def _tab_headers(name: str, anchor: str):
        """A tab whose header row can't be located (or that lacks a Score
        column) yields no stated grains — H4 then rejects quotes at that
        grain rather than the whole package failing to ingest."""
        if name not in wb.sheetnames:
            return None, None, None
        ws = wb[name]
        try:
            headers, first = _header_map(ws, anchor)
        except ValueError:
            return None, None, None
        if "score" not in headers:
            return None, None, None
        return ws, headers, first

    try:
        ws, headers, first = _tab_headers("Pillar_Summary", "Pillar")
        if headers is not None:
            for r, row in enumerate(ws.iter_rows(min_row=first, values_only=True), first):
                def v(key, _row=row):
                    i = headers.get(key)
                    return _row[i] if i is not None and i < len(_row) else None
                pid = str(v("pillar") or "").strip()
                if not _PILLAR_RE.match(pid):
                    continue
                score_col = openpyxl.utils.get_column_letter(headers["score"] + 1)
                out["pillars"].append({
                    "pillar_id": pid,
                    "name": (str(v("pillar_name")).strip() if v("pillar_name") else None),
                    "score": _num(v("score")),
                    "weight": _num(v("weight_ib")),
                    "peer_median": _num(v("peer_median")),
                    "source_cell": f"Pillar_Summary!{score_col}{r}",
                })
        ws, headers, first = _tab_headers("Category_Detail", "Category_ID")
        if headers is not None:
            for r, row in enumerate(ws.iter_rows(min_row=first, values_only=True), first):
                def v(key, _row=row):
                    i = headers.get(key)
                    return _row[i] if i is not None and i < len(_row) else None
                cid = str(v("category_id") or "").strip()
                if not _CATEGORY_RE.match(cid):
                    continue
                score_col = openpyxl.utils.get_column_letter(headers["score"] + 1)
                out["categories"].append({
                    "category_id": cid,
                    "name": (str(v("category_name")).strip() if v("category_name") else None),
                    "pillar_id": (str(v("pillar")).strip() if v("pillar") else cid.split("C")[0]),
                    "score": _num(v("score")),
                    "peer_median": _num(v("peer_median")),
                    "priority_score": _num(v("priority_score")),
                    "priority_tier": (str(v("priority_tier")).strip() if v("priority_tier") else None),
                    "source_cell": f"Category_Detail!{score_col}{r}",
                })
        return out
    finally:
        wb.close()


def _num(value):
    d = _decimal(value)
    return None if d in (None, "UNPARSEABLE") else float(d)


def parse_peer_benchmarks(path: str) -> list:
    """Peer_Benchmarks is CATEGORY grain with named-peer columns after the
    stat block. Only the per-peer scores are data — Entity_Score and the
    stat columns (median/quartiles/min/max/delta) are derivable, so they
    are read solely to verify, never to store (counts are computed, never
    stored, where a source of truth exists). Stops at the footer notes."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if "Peer_Benchmarks" not in wb.sheetnames:
            return []
        ws = wb["Peer_Benchmarks"]
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if not header:
            return []
        stats = {"category", "category_name", "entity_score", "peer_median",
                 "peer_p25", "peer_p75", "peer_min", "peer_max", "delta_vs_median"}
        peer_cols = [(i, str(h).strip()) for i, h in enumerate(header)
                     if h is not None and _norm(str(h)) not in stats]
        # Non-numeric cells ("N/A", footnotes) are None here — a peer grid
        # is data or nothing, and downstream median verification sorts
        # these values.
        num = (lambda v: None if (d := _decimal(v)) in (None, "UNPARSEABLE") else d)
        out = []
        for row in rows:
            if not row:   # read-only mode yields () for blank rows
                continue
            cat = str(row[0] or "").strip()
            if not _CATEGORY_RE.match(cat):
                continue
            def col(key):
                for i, h in enumerate(header):
                    if h is not None and _norm(str(h)) == key:
                        return row[i] if i < len(row) else None
                return None
            out.append({
                "category_id": cat,
                "category_name": (str(row[1]).strip() if len(row) > 1 and row[1] else None),
                "entity_score": num(col("entity_score")),
                "stated_median": num(col("peer_median")),
                "peers": [(name, num(row[i]) if i < len(row) else None)
                          for i, name in peer_cols],
            })
        return out
    finally:
        wb.close()


def parse_recommendations(path: str) -> list:
    """The Recommendations tab lands raw: rec_id as it arrived (the raw
    tier preserves package identifiers) plus the full row as payload."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if "Recommendations" not in wb.sheetnames:
            return []
        ws = wb["Recommendations"]
        rows = ws.iter_rows(values_only=True)
        first = next(rows, None)
        if not first:
            return []
        header = [(_norm(str(h)) if h is not None else None) for h in first]
        out = []
        for row in rows:
            if not row:   # read-only mode yields () for blank rows
                continue
            rec_id = str(row[0] or "").strip()
            if not rec_id.upper().startswith("REC-"):
                continue
            payload = {header[i]: (str(row[i]).strip() if i < len(row) and row[i] is not None else None)
                       for i in range(len(header)) if header[i]}
            out.append({"rec_id": rec_id, "payload": payload})
        return out
    finally:
        wb.close()
