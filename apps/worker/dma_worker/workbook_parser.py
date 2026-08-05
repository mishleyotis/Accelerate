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
        cols = {k: _pick(headers, names) for k, names in _EV_ALIASES.items()}
        cols["e_id"] = _pick(headers, ("evidence_id", "e_id"))
        out = []
        for row in ws.iter_rows(min_row=first, values_only=True):
            def v(key):
                i = cols.get(key)
                return row[i] if i is not None and i < len(row) else None
            e_id = str(v("e_id") or "").strip()
            if not e_id.startswith("E-"):
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
        return out
    finally:
        wb.close()


# A fact-grain citation and the header the research workbook puts in front of
# an excerpt block: "[ERS: 4.20] [FACT] [E-012:F1] Source (T2, CURRENT): text".
_RW_FACT_RE = re.compile(r"\[(E-\d+):(F\d+)\]\s*")
_RW_HEAD_RE = re.compile(r"^\s*\[ERS:\s*([\d.]+)\]\s*(?:\[([A-Z_]+)\]\s*)?")
_RW_SRC_PREFIX_RE = re.compile(r"^[^:]{0,120}?\((T[1-5]),\s*[A-Z_]+\):\s*")
_RW_DETAIL_TABS = ("P1_Scoring_Detail", "P2_Scoring_Detail",
                   "P3_Scoring_Detail", "P4_Scoring_Detail")


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
        frag = _RW_SRC_PREFIX_RE.sub("", text[m.end():end].strip()).strip(" ;·")
        if frag:
            out[f"{m.group(1)}:{m.group(2)}"] = frag
    return out


def parse_research_workbook(path: str) -> dict:
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
        ws, headers, first = tab("Evidence_Linkage_Matrix", "Evidence_ID")
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
        for name in _RW_DETAIL_TABS:
            ws, headers, first = tab(name, "SubCap_ID")
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
        ws, headers, first = tab("Caps_Applied_Log", "SubCap_ID")
        if headers is not None:
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
                out["caps"].append({
                    "subcap_id": sid,
                    "cap_type": (str(v("cap_type")).strip() if v("cap_type") else None),
                    "cap_reason": (str(v("cap_reason")).strip() if v("cap_reason") else None),
                    "pre_cap_score": _num(v("pre_cap_score")),
                    "post_cap_score": _num(v("post_cap_score")),
                    "e_id": (str(v("evidence_id", "e_id")).strip()
                             if v("evidence_id", "e_id") else None),
                })

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
        for link in out["links"]:
            for fact_id, text in link["excerpts"].items():
                e_id = fact_id.split(":")[0]
                if len(text) >= 50 and len(text) > len(best.get(e_id, "")):
                    best[e_id] = text
        for item in out["ledger"]:
            if best.get(item["e_id"]):
                item["excerpt"] = best[item["e_id"]][:500]
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
            if len(frag) < 20:
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


def _stat_key(header: str):
    """The canonical stat a header names, or None when it names a peer."""
    return _STAT_ALIASES.get(_norm(header))


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
                    "source_cell": f"Pillar_Summary!{score_col}{r}",
                })
        ws, headers, first = _tab_headers("Category_Detail", "Category_ID")
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
        # A stat column is not a peer. The corpus writes these headers both
        # ways — `Peer_Median` in some packages, a bare `Median` in others —
        # and a name that misses this map becomes a PEER NAMED "Median",
        # which is how 54 of BCU's 144 peer rows arrived as institutions
        # called Median, P25 and P75.
        peer_cols = [(i, str(h).strip()) for i, h in enumerate(header)
                     if h is not None and _stat_key(str(h)) is None]

        def col(canonical):
            """The row's value for a canonical stat, under any of its aliases."""
            for i, h in enumerate(header):
                if h is not None and _stat_key(str(h)) == canonical:
                    return row[i] if i < len(row) else None
            return None
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
            # The name comes from the column that declares itself a name.
            # Reading row[1] positionally put a peer's SCORE in the name
            # field whenever the tab has no Category_Name column.
            cat_name = col("category_name")
            out.append({
                "category_id": cat,
                "category_name": (str(cat_name).strip() or None) if cat_name is not None else None,
                "entity_score": num(col("entity_score")),
                "stated_median": num(col("median")),
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
        for row in rows:
            if not row:   # read-only mode yields () for blank rows
                continue
            raw = str(row[0] or "").strip()
            if not raw:
                continue
            payload = {header[i]: (str(row[i]).strip() if i < len(row) and row[i] is not None else None)
                       for i in range(len(header)) if header[i]}
            # a row whose only populated cell is the id is a footer or spacer
            if not any(v for k, v in payload.items() if k != header[0]):
                continue
            rec_id = f"REC-{raw}" if id_is_rank or not raw.upper().startswith("REC-") else raw
            if rec_id in seen:
                continue
            seen.add(rec_id)
            out.append({"rec_id": rec_id, "payload": payload})
        return out
    finally:
        wb.close()
