"""Schema-tolerant recommendations reader.

The corpus ships recommendations under several filenames AND several
schemas. The original `parse_recommendations` only handled the
`recommendations_detail.json` shape, so the 37 packages shipping
`recommendations.json` and 13 shipping `06_recommendations.json` parsed to
ZERO recs — an empty D4 Platform page. This normalizes every known shape
into `RecommendationRow`, mapping each into the keys the persistence layer
(`_rec_description` + `target_subcap_ids` regex) reads.

Shapes handled:
  A. detail / register (canonical):
       {recommendations:[{id, priority, title, root_cause:{...},
        solution:{description}, cross_pillar_unlock, counter_arguments}]}
  B. phase-6 export (`recommendations.json`):
       {recommendations:[{rec_id, title, priority_gap, evidence_ids,
        root_cause:<str>, solution_rationale, zennify_solution_names}]}
  C. `06_recommendations.json`:
       {recommendations:[{id:"R1", title, priority_rank, horizon,
        root_cause:{narrative, evidence_ids}, solution_fit:{...},
        zennify_solution:<str>, cross_pillar_unlocks:[...],
        counter_argument:{...}}]}

Pure / no DB. Returns [] on malformed input — a bad rec file never aborts.
"""
from __future__ import annotations

import json
from typing import Any

from app.schemas.package import RecommendationRow


def _rec_id(raw: Any) -> str:
    """Normalise REC-01 / R7 / 3 / rec_id=1 → `REC-NN` (matches the
    canonical parser so D4 ids are stable across schema variants)."""
    rid = str(raw if raw is not None else "").strip()
    if rid and not rid.upper().startswith("REC-"):
        digits = "".join(ch for ch in rid if ch.isdigit())
        return f"REC-{int(digits):02d}" if digits else rid
    return rid


def _as_text(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, list | tuple):
        joined = "; ".join(str(x).strip() for x in v if str(x).strip())
        return joined or None
    return str(v)


def _normalize_rec(rec: dict[str, Any], index: int | None = None) -> dict[str, Any] | None:
    if not isinstance(rec, dict):
        return None
    # Capitalised-key variant (recommendation_summary.json: Rec_ID, Title,
    # Zennify_Solution, Root_Cause, Evidence_IDs, Priority, …). Lower-case the
    # top-level keys so the canonical (lowercase) reads below find them. A
    # genuine lowercase key already present wins over a capitalised duplicate.
    if any(k[:1].isupper() for k in rec if isinstance(k, str)):
        _lc: dict[str, Any] = {}
        for k, v in rec.items():
            lk = k.lower() if isinstance(k, str) else k
            if lk not in rec:               # don't clobber an existing lowercase key
                _lc.setdefault(lk, v)
        rec = {**_lc, **{k: v for k, v in rec.items() if not (isinstance(k, str) and k[:1].isupper())}}
    # Many variants ship NO id/rec_id (Rockland/Baxter are positional;
    # Manasquan uses `rank`). Synthesise from rank, then row index, so the
    # rec isn't dropped — REC-NN is display/ordering only.
    rid = _rec_id(
        rec.get("id") or rec.get("rec_id") or rec.get("rank")
        or (index + 1 if index is not None else None)
    )
    if not rid:
        return None
    out = dict(rec)  # preserve extras (RecommendationRow has extra='allow')

    # Lettered-section schema (recommendations.json variant: `solution` +
    # A_priority_score / B_root_cause / C_peer_gap_assessment /
    # D_zennify_offering_alignment / F_counter_argument / gap_categories). Map
    # its fields onto the canonical keys so the title, root cause and target
    # subcaps come from the REPORT instead of "(untitled)" with a NULL platform
    # (2026-07-15 verbatim QA: 1st Security Bank shipped 7 untitled recs whose
    # `solution` — "Financial Services Cloud + Service Cloud" etc. — was never
    # read into the title).
    # NB: the capitalised-key fold above already lowercased A_/B_/C_/F_ → a_/b_/…
    _brc = rec.get("b_root_cause")
    if _brc and not rec.get("root_cause"):
        _fnd = (_as_text(_brc.get("summary") or _brc.get("narrative"))
                if isinstance(_brc, dict) else _as_text(_brc))
        rec["root_cause"] = {
            "finding": _fnd,
            "evidence_ids": (_brc.get("evidence_ids")
                             if isinstance(_brc, dict) else None),
        }
    if rec.get("f_counter_argument") and not rec.get("counter_arguments"):
        rec["counter_arguments"] = rec["f_counter_argument"]
    if rec.get("gap_categories") and not rec.get("target_categories"):
        rec["target_categories"] = rec["gap_categories"]

    # root_cause → dict carrying `finding` + `scoring_impact` (the keys
    # _rec_description reads + the regex that mines target subcap ids).
    rc_raw = rec.get("root_cause")
    rc: dict[str, Any] = {}
    if isinstance(rc_raw, dict):
        rc = dict(rc_raw)
        if "finding" not in rc and rc.get("narrative"):
            rc["finding"] = rc["narrative"]
    elif isinstance(rc_raw, str):
        rc = {"finding": rc_raw}
    if not rc.get("scoring_impact"):
        ctx = " ".join(filter(None, (
            rc.get("finding"),
            _as_text(rec.get("priority_gap")),
            _as_text(rec.get("gaps")),
            _as_text(rec.get("target_categories")),
            _as_text(rec.get("pillar_alignment")),
        )))
        if ctx.strip():
            rc["scoring_impact"] = ctx.strip()
    # Top-level evidence_ids (capitalised-variant Evidence_IDs) → fold into
    # root_cause so the fit evidence extractor + citations find them.
    if not rc.get("evidence_ids") and rec.get("evidence_ids"):
        ev = rec["evidence_ids"]
        rc["evidence_ids"] = ev if isinstance(ev, list) else [ev]

    # solution → dict carrying `description`.
    sol_raw = rec.get("solution")
    sol: dict[str, Any] = dict(sol_raw) if isinstance(sol_raw, dict) else {}
    if not sol.get("description"):
        desc = (
            (sol_raw if isinstance(sol_raw, str) else None)
            or _as_text(rec.get("solution_rationale"))
            or _as_text(rec.get("zennify_solution"))
            or _as_text(rec.get("zennify_solution_names"))
        )
        if desc:
            sol["description"] = desc
    if isinstance(rec.get("solution_fit"), dict) and "fit" not in sol:
        sol["fit"] = rec["solution_fit"]

    # counter_arguments → list[dict].
    ca_raw = rec.get("counter_arguments") or rec.get("counter_argument")
    if isinstance(ca_raw, dict):
        counter = [ca_raw]
    elif isinstance(ca_raw, list):
        counter = [c for c in ca_raw if isinstance(c, dict)]
    else:
        counter = []

    priority = rec.get("priority") or rec.get("horizon") or rec.get("priority_rank")
    # The lettered schema ships no priority/horizon/priority_rank key, so
    # priority_rank would persist NULL and the downstream recommendation-driven
    # fit's priority factor collapses to worst-case. Recs are listed
    # most-urgent-first, so fall back to the 1-based list position (a bare rank
    # `_priority_rank` reads as N) — never let the rank go NULL when we know the
    # analyst's own ordering.
    if priority is None and index is not None:
        priority = str(index + 1)

    # Coerce the remaining TYPED fields so a variant schema's same-named key
    # (e.g. expected_outcomes as list[str] in the phase-6 export vs the
    # detail schema's list[dict]) can't fail RecommendationRow validation.
    eo_raw = rec.get("expected_outcomes")
    expected_outcomes = (
        [e if isinstance(e, dict) else {"outcome": str(e)} for e in eo_raw]
        if isinstance(eo_raw, list) else []
    )
    so_raw = rec.get("strategic_objectives")
    strategic_objectives = (
        [str(s) for s in so_raw] if isinstance(so_raw, list) else []
    )
    pb_raw = rec.get("peer_benchmark")
    peer_benchmark = pb_raw if isinstance(pb_raw, dict) else None

    out.update({
        "id": rid,
        "title": (
            rec.get("title") or rec.get("recommendation") or rec.get("name")
            or rec.get("category") or rec.get("priority_category")
            # `solution` (a string in the lettered schema) is the analyst's own
            # named recommendation — use it as the headline before giving up
            # (2026-07-15: was the sole title source for 1st Security's recs).
            or (rec.get("solution") if isinstance(rec.get("solution"), str) else None)
            or "(untitled)"
        ),
        "priority": str(priority) if priority is not None else None,
        "ownership": _as_text(rec.get("ownership")),
        "technographic_status": _as_text(rec.get("technographic_status")),
        "root_cause": rc or None,
        "solution": sol or None,
        "peer_benchmark": peer_benchmark,
        "cross_pillar_unlock": _as_text(
            rec.get("cross_pillar_unlock") or rec.get("cross_pillar_unlocks")
        ),
        "counter_arguments": counter,
        "expected_outcomes": expected_outcomes,
        "strategic_objectives": strategic_objectives,
    })

    # Part 7.2 (migration 048): mine feature / phase / root-cause E-IDs /
    # quantified outcomes / dependency edges from the raw rec so every
    # RecommendationRow (extra='allow') carries them for the persist +
    # derive layers. Extraction is pure + shape-tolerant (rec_files).
    from app.services.parsers.rec_files import extract_rec_enrichment
    enrich = extract_rec_enrichment({**rec, "id": rid})
    out.update({
        "feature": enrich["feature"],
        "phase": enrich["phase"],
        "root_cause_e_ids": enrich["root_cause_e_ids"],
        "outcomes": enrich["outcomes"],
        # Dependencies THIS rec requires → the typed prerequisite_rec_ids
        # column; inverse edges ride as an extra for the writer to fan out.
        "prerequisite_rec_ids": enrich["requires_rec_ids"],
        "prereq_of_rec_ids": enrich["prereq_of_rec_ids"],
    })
    return out


def parse_recommendations_any(blob: str) -> list[RecommendationRow]:
    """Parse any known recommendations schema → list[RecommendationRow]."""
    try:
        d = json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(d, list):
        recs = d
    elif isinstance(d, dict):
        recs = d.get("recommendations") or d.get("items") or []
    else:
        recs = []
    out: list[RecommendationRow] = []
    seen: set[str] = set()
    for i, rec in enumerate(recs):
        norm = _normalize_rec(rec, i)
        if norm is None or norm["id"] in seen:
            continue
        try:
            out.append(RecommendationRow(**norm))
            seen.add(norm["id"])
        except Exception:
            continue
    return out
