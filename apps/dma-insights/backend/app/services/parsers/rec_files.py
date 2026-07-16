# ruff: noqa: RUF001, RUF002
# This module matches (and emits windows over) corpus prose that uses real
# en/em dashes; the regex character classes must keep them.
"""Rich-recommendation enrichment parser (Part 7.2).

The corpus' richest rec sources — `recommendations_detail.json` (Alma
canonical) and per-REC `08_appendices/recommendations/REC-NN.json`
files (CACU shape) — were never mined for the fields the D4
RecommendationModal renders: the concrete platform `feature`, the
sequencing `phase`, the `root_cause_e_ids` grounding the rec, the
quantified `outcomes {time, effort, metric, peer}` and the
`prerequisite_rec_ids` dependency edges. Migration 048 added the
columns; this module extracts the values from EVERY known rec shape:

  - structured keys when the source ships them (evidence_ids arrays,
    zennify_offering, expected_outcomes with baseline/target,
    peer_benchmark.peer, tier/priority/horizon),
  - deterministic NLP over the rec prose otherwise (E-ID citation
    regex, nlp.quantities for durations/metrics, dependency-clause
    patterns for "R7 is the prerequisite for R1-R6" / "REC-10 …
    requires … as prerequisite").

Consumers:
  - `package_recommendations._normalize_rec` attaches the extracted
    fields to each RecommendationRow (extra='allow') at parse time.
  - `derive_recommendations` re-reads package rec sources from the
    fixture corpus and UPDATEs the 048 columns for persisted rows.
  - `parse_rec_dir` ingests per-REC directories the aggregate-filename
    globs never matched (the audit's "rich corpus exists ONLY in
    tests/fixtures — never ingested").

Pure / no DB. Every function returns honest None/[] when the source
carries no signal — nothing is fabricated.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.services.nlp import patterns as nlp_patterns
from app.services.nlp.quantities import extract_metrics

# ── pattern-registry fingerprints (report-agnosticism, Part 2) ─────────
nlp_patterns.register(
    {"filename_regex": r"^REC-\d{1,3}\.json$",
     "keys": ["id", "title", "root_cause"]},
    "rec_file_json",
)
nlp_patterns.register(
    {"filename_regex": r"recommendations_detail\.json$",
     "keys": ["recommendations"]},
    "rec_detail_json",
)

_E_ID_RE = re.compile(r"\bE-[A-Z0-9][A-Z0-9-]{0,14}\b")
_REC_ID_RE = re.compile(r"\b(?:REC[-\s]?\d{1,3}|R[-\s]?\d{1,3})\b", re.IGNORECASE)
_REC_RANGE_RE = re.compile(
    r"\b(?:REC[-\s]?|R[-\s]?)(\d{1,3})\s*[-–—]\s*(?:REC[-\s]?|R[-\s]?)?(\d{1,3})\b",
    re.IGNORECASE,
)
_PHASE_RE = re.compile(r"\bphase\s*(\d)\b", re.IGNORECASE)
_TIER_RE = re.compile(r"\bT(\d)\b")
_PRIORITY_RE = re.compile(r"\bP(\d)\b")
_HORIZON_RE = re.compile(r"\b(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:mo|month)", re.IGNORECASE)
_DURATION_RE = re.compile(
    r"\b\d{1,2}\s*[-–]\s*\d{1,2}\s*(?:months?|weeks?)\b|\b\d{1,2}\s*(?:months?|weeks?)\b",
    re.IGNORECASE,
)

# Known Zennify-relevant platform features, scanned against title +
# solution text when no structured offering key ships. Order matters —
# more specific first.
_FEATURE_KEYWORDS: list[tuple[str, re.Pattern[str]]] = [
    ("Financial Services Cloud", re.compile(r"financial services cloud|\bFSC\b", re.I)),
    ("Data Cloud", re.compile(r"data cloud", re.I)),
    ("Marketing Cloud", re.compile(r"marketing cloud", re.I)),
    ("Service Cloud", re.compile(r"service cloud", re.I)),
    ("Sales Cloud", re.compile(r"sales cloud", re.I)),
    ("Experience Cloud", re.compile(r"experience cloud", re.I)),
    ("Agentforce", re.compile(r"agentforce", re.I)),
    ("MuleSoft Anypoint", re.compile(r"mulesoft|anypoint", re.I)),
    ("Salesforce Shield", re.compile(r"\bshield\b", re.I)),
    ("CRM Analytics", re.compile(r"crm analytics", re.I)),
    ("Tableau Pulse", re.compile(r"tableau pulse", re.I)),
    ("Tableau", re.compile(r"tableau", re.I)),
    ("Mosaic AI", re.compile(r"mosaic", re.I)),
    ("Databricks Lakehouse", re.compile(r"lakehouse|databricks", re.I)),
    ("nCino Workflow Engine", re.compile(r"workflow engine", re.I)),
    ("nCino", re.compile(r"ncino", re.I)),
    ("Twilio Engage", re.compile(r"twilio engage|\bengage\b", re.I)),
    ("Twilio Flex", re.compile(r"twilio flex|\bflex\b", re.I)),
    ("Twilio Segment", re.compile(r"\bsegment\b", re.I)),
    ("Twilio", re.compile(r"twilio", re.I)),
    ("Slack", re.compile(r"\bslack\b", re.I)),
    ("Digital Strategy Workshop", re.compile(r"strategy workshop", re.I)),
    ("GRC Platform", re.compile(r"\bGRC\b", re.I)),
]


def _as_texts(*values: Any) -> list[str]:
    out: list[str] = []
    for v in values:
        if isinstance(v, str) and v.strip():
            out.append(v)
        elif isinstance(v, list | tuple):
            out.extend(x for x in v if isinstance(x, str) and x.strip())
        elif isinstance(v, dict):
            out.extend(x for x in v.values() if isinstance(x, str) and x.strip())
    return out


def _norm_rec_id(raw: str) -> str:
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    return f"REC-{int(digits):02d}" if digits else str(raw).upper()


def extract_feature(rec: dict) -> str | None:
    """Concrete platform feature the rec ships (distinct from the title)."""
    sol = rec.get("solution") if isinstance(rec.get("solution"), dict) else {}
    for key in ("zennify_offering", "offering", "feature"):
        v = (sol or {}).get(key) or rec.get(key)
        if isinstance(v, str) and v.strip():
            return re.sub(r"^#?\d+\s*", "", v.strip())[:120]
    zs = rec.get("zennify_solution") or rec.get("zennify_solution_names")
    if isinstance(zs, list):
        zs = zs[0] if zs else None
    if isinstance(zs, str) and zs.strip():
        return re.sub(r"^#?\d+\s*", "", zs.strip())[:120]
    hay = " ".join(_as_texts(
        rec.get("title"), (sol or {}).get("description"), (sol or {}).get("narrative"),
    ))
    for name, rx in _FEATURE_KEYWORDS:
        if rx.search(hay):
            return name
    return None


def extract_phase(rec: dict) -> int | None:
    """Sequencing phase 1..4 from explicit phase / tier / priority / horizon."""
    for key in ("phase", "sequencing_phase"):
        v = rec.get(key)
        if isinstance(v, int) and 1 <= v <= 4:
            return v
        if isinstance(v, str):
            m = _PHASE_RE.search(v)
            if m:
                return max(1, min(4, int(m.group(1))))
    seq = rec.get("sequencing")
    if isinstance(seq, dict):
        v = seq.get("phase")
        if isinstance(v, int) and 1 <= v <= 4:
            return v
    tier = rec.get("tier")
    if isinstance(tier, str):
        m = _TIER_RE.search(tier)
        if m:
            return max(1, min(4, int(m.group(1))))
    prio = rec.get("priority") or rec.get("horizon")
    if isinstance(prio, str):
        m = _HORIZON_RE.search(prio)
        if m:
            start = int(m.group(1))
            return 1 if start < 6 else 2 if start < 12 else 3 if start < 18 else 4
        m = _PRIORITY_RE.search(prio)
        if m:
            return max(1, min(4, int(m.group(1)) + 1))
        up = prio.upper()
        if "IMMEDIATE" in up or "QUICK" in up:
            return 1
        if "NEAR" in up or "SHORT" in up:
            return 2
        if "MEDIUM" in up or "MID" in up:
            return 3
        if "LONG" in up:
            return 4
    return None


def extract_root_cause_e_ids(rec: dict) -> list[str]:
    """E-IDs grounding the root cause — structured arrays first, then the
    citation regex over the root-cause prose. Order-preserving dedupe."""
    rc = rec.get("root_cause") if isinstance(rec.get("root_cause"), dict) else {}
    ordered: list[str] = []
    for key in ("evidence_ids", "evidence"):
        v = (rc or {}).get(key)
        if isinstance(v, list):
            ordered.extend(str(x) for x in v if isinstance(x, str))
    ordered.extend(
        str(x) for x in (rec.get("evidence_ids") or [])
        if isinstance(x, str)
    )
    prose = " ".join(_as_texts(
        rc, rec.get("root_cause") if isinstance(rec.get("root_cause"), str) else None,
    ))
    ordered.extend(_E_ID_RE.findall(prose))
    seen: set[str] = set()
    out: list[str] = []
    for e in ordered:
        e = e.strip()
        if e.startswith("E-") and e not in seen:
            seen.add(e)
            out.append(e)
    return out[:12]


def _best_outcome(outcomes: list) -> dict | None:
    """Prefer an expected_outcome with a numeric baseline→target."""
    dicts = [o for o in outcomes if isinstance(o, dict)]
    for o in dicts:
        base, tgt = str(o.get("baseline") or ""), str(o.get("target") or "")
        if re.search(r"\d", base) and re.search(r"\d", tgt) and o.get("metric"):
            return o
    for o in dicts:
        if o.get("metric"):
            return o
    return dicts[0] if dicts else None


def extract_outcomes(rec: dict, *, effort_band: str | None = None) -> dict | None:
    """Quantified expected outcomes {time, effort, metric, peer}."""
    sol = rec.get("solution") if isinstance(rec.get("solution"), dict) else {}
    eo = rec.get("expected_outcomes") if isinstance(rec.get("expected_outcomes"), list) else []

    # time — explicit duration in the solution/outcome prose.
    time_hay = " ".join(_as_texts(
        (sol or {}).get("approach"), (sol or {}).get("implementation_approach"),
        (sol or {}).get("description"), (sol or {}).get("narrative"),
        rec.get("timeline"), rec.get("time_to_value"),
        [str(o.get("business_impact") or "") for o in eo if isinstance(o, dict)],
    ))
    m = _DURATION_RE.search(time_hay)
    time_txt = m.group(0).strip() if m else None
    if time_txt is None:
        phase = extract_phase(rec)
        if phase:
            time_txt = {1: "0–6 months", 2: "6–12 months",
                        3: "12–18 months", 4: "18+ months"}[phase]

    # effort — explicit only (writer layers add effort-band fallbacks).
    effort = rec.get("effort") or rec.get("effort_band") or effort_band
    effort_txt = None
    if isinstance(effort, str) and effort.strip():
        up = effort.strip().upper()
        effort_txt = {"SMALL": "S", "MEDIUM": "M", "LARGE": "L", "XLARGE": "XL"}.get(up, up[:2])

    # metric — best structured expected_outcome, else quantities over prose.
    metric_txt = None
    best = _best_outcome(eo)
    if best:
        base, tgt = best.get("baseline"), best.get("target")
        if base and tgt:
            metric_txt = f"{best.get('metric')}: {base} → {tgt}"
        else:
            metric_txt = str(
                best.get("metric") or best.get("business_impact") or ""
            ).strip() or None
    if not metric_txt:
        prose = " ".join(_as_texts(
            [str(o) for o in eo], (sol or {}).get("description"),
        ))
        metrics = extract_metrics(prose)
        if metrics:
            m0 = metrics[0]
            label = m0.get("metric") or "outcome"
            metric_txt = f"{label} {m0.get('raw') or m0.get('value')}".strip()
    if metric_txt:
        metric_txt = metric_txt[:160]

    # peer — the named benchmark peer.
    peer_txt = None
    pb = rec.get("peer_benchmark")
    if isinstance(pb, dict):
        p = pb.get("peer") or pb.get("peer_name")
        if isinstance(p, str) and p.strip():
            peer_txt = p.strip()[:120]

    out = {"time": time_txt, "effort": effort_txt, "metric": metric_txt, "peer": peer_txt}
    return out if any(out.values()) else None


def extract_dependencies(rec: dict, rec_id: str) -> tuple[list[str], list[str]]:
    """Dependency mining → (requires, prereq_of), both REC-NN-normalised.

    ``requires``: rec ids THIS rec depends on (→ prerequisite_rec_ids).
    ``prereq_of``: rec ids that depend on THIS rec (the writer inverts
    them onto the other rows' prerequisite_rec_ids).
    """
    requires: list[str] = []
    prereq_of: list[str] = []
    self_id = _norm_rec_id(rec_id)

    for key in ("prerequisite_rec_ids", "prerequisites", "depends_on"):
        v = rec.get(key)
        if isinstance(v, list):
            requires.extend(
                _norm_rec_id(x) for x in v
                if isinstance(x, str) and _REC_ID_RE.fullmatch(x.strip())
            )

    texts = _as_texts(
        rec.get("cross_pillar_unlock"), rec.get("cross_pillar_unlocks"),
        rec.get("root_cause"), rec.get("solution"),
        rec.get("sequencing"),
    )
    for sentence in re.split(r"[.;\n]", " ".join(texts)):
        ids_in = [_norm_rec_id(m.group(0)) for m in _REC_ID_RE.finditer(sentence)]
        low = sentence.lower()

        # "R7 is the organizational prerequisite for R1-R6"
        if "prerequisite for" in low or "prereq for" in low:
            tail = sentence[low.index("for") + 3:]
            targets = [_norm_rec_id(m.group(0)) for m in _REC_ID_RE.finditer(tail)]
            for m in _REC_RANGE_RE.finditer(tail):
                lo, hi = int(m.group(1)), int(m.group(2))
                if 0 < lo <= hi <= lo + 24:
                    targets.extend(f"REC-{i:02d}" for i in range(lo, hi + 1))
            prereq_of.extend(t for t in targets if t != self_id)
            continue

        if "requires" in low or "depends on" in low or "must land" in low:
            cut = min(
                i for i in (
                    low.find("requires"), low.find("depends on"),
                    low.find("must land"),
                )
                if i >= 0
            )
            before = sentence[:cut]
            subject_ids = [_norm_rec_id(m.group(0))
                           for m in _REC_ID_RE.finditer(before)]
            after_ids = [i for i in ids_in if i not in subject_ids]
            if subject_ids and subject_ids[0] != self_id:
                # "REC-10 … requires <this rec's output> as prerequisite"
                # → REC-10 depends on THIS rec.
                if "prerequisite" in low or self_id in after_ids or not after_ids:
                    prereq_of.append(subject_ids[0])
            else:
                # "<this rec> requires REC-04 …" → THIS depends on those.
                requires.extend(i for i in after_ids if i != self_id)

    def _dedupe(xs: list[str]) -> list[str]:
        seen: set[str] = set()
        out = []
        for x in xs:
            if x and x != self_id and x not in seen:
                seen.add(x)
                out.append(x)
        return out

    return _dedupe(requires), _dedupe(prereq_of)


def extract_rec_enrichment(rec: dict, *, effort_band: str | None = None) -> dict:
    """All migration-048 fields (+ dependency edges) for one raw rec dict."""
    rec_id = str(rec.get("id") or rec.get("rec_id") or "")
    requires, prereq_of = extract_dependencies(rec, rec_id)
    return {
        "feature": extract_feature(rec),
        "phase": extract_phase(rec),
        "root_cause_e_ids": extract_root_cause_e_ids(rec),
        "outcomes": extract_outcomes(rec, effort_band=effort_band),
        "requires_rec_ids": requires,
        "prereq_of_rec_ids": prereq_of,
    }


def feature_from_text(text: str) -> str | None:
    """Keyword-scan a rec title/description for the concrete platform
    feature it ships (the mining tier for recs whose source JSON is gone)."""
    for name, rx in _FEATURE_KEYWORDS:
        if rx.search(text or ""):
            return name
    return None


_EFFORT_PHASE = {"SMALL": 1, "S": 1, "MEDIUM": 2, "M": 2,
                 "LARGE": 3, "L": 3, "XLARGE": 4, "XL": 4}
_PHASE_WINDOW = {1: "0–6 months", 2: "6–12 months",
                 3: "12–18 months", 4: "18+ months"}
_EFFORT_LETTER = {"SMALL": "S", "MEDIUM": "M", "LARGE": "L", "XLARGE": "XL"}


def effort_band_from_gap(gap: float) -> str:
    """Grounded effort band from the maturity gap — a bigger climb to M4 is
    a bigger build. Mirrors derive_recommendations._effort_band so the two
    fill tiers agree."""
    if gap >= 1.5:
        return "LARGE"
    if gap >= 0.75:
        return "MEDIUM"
    return "SMALL"


def compose_score_metric(
    label: str, current: float, *, target: float = 4.0,
    peer_median: float | None = None,
) -> str:
    """The grounded maturity-outcome metric — ``'<label> score <cur> → <tgt>
    (peer median <pm>)'``. It carries its own quantified lift inside the
    ``cur → tgt`` clause so the roadmap's ``_lift_from_metric`` recovers the
    per-rec ``maturity_lift`` with no extra plumbing."""
    m = f"{label} score {current:.2f} → {target:.1f}"
    if peer_median is not None:
        m += f" (peer median {peer_median:.2f})"
    return m[:160]


def compose_gap_outcomes(
    *, label: str, current: float, target: float = 4.0,
    peer_median: float | None = None, effort_band: str | None = None,
    peer_name: str | None = None,
) -> dict:
    """Grounded ``{time, effort, metric, peer}`` from a REAL maturity gap —
    the fill tier for recs whose corpus prose carried no explicit outcome.
    Every value traces to a real score (current / target / peer_median), the
    gap-derived effort band, or a real peer name; nothing is invented."""
    eb = (effort_band or effort_band_from_gap(max(0.0, target - current))).upper()
    phase = _EFFORT_PHASE.get(eb, 2)
    return {
        "time": _PHASE_WINDOW.get(phase),
        "effort": _EFFORT_LETTER.get(eb, (eb[:2] if eb else None)),
        "metric": compose_score_metric(
            label, current, target=target, peer_median=peer_median),
        "peer": peer_name,
    }
_PEER_SENT_RE = re.compile(r"[^.;\n]*\bpeer\b[^.;\n]*", re.IGNORECASE)
# "P4C1 scores 2.1 vs peer 3.0" — the maturity-score clause analyst prose
# and the derived-rec grounding both use; for a category-gap rec that IS
# the quantified outcome metric.
_SCORE_CLAUSE_RE = re.compile(
    r"\b(P[1-4]C\d+(?:\.\d+)*)\s+scores?\s+(\d(?:\.\d+)?)"
    r"(?:\s+vs\.?\s+peer(?:\s+median)?\s+(\d(?:\.\d+)?))?",
    re.IGNORECASE,
)
# The rec's OWN declared maturity transition — "P2C1 (1.79→2.8)",
# "P4C2 (Analytics & AI): 2.65 → 3.4", "P2C1: 2.0 -> 3.0". The optional
# name-parenthetical excludes digits/arrows so "(1.79→2.8)" is always
# read as the transition, never swallowed as a name.
_SCORE_TRANSITION_RE = re.compile(
    r"\b(P[1-4]C\d+(?:\.\d+)*)"
    r"(?:\s*\([^)0-9→]{0,40}\))?"
    r"\s*[:(]?\s*"
    r"(\d(?:\.\d+)?)\s*(?:→|->)\s*(\d(?:\.\d+)?)"
)


def extract_score_transitions(text: str) -> list[dict]:
    """Every ``P?C? current → target`` maturity transition the rec's own
    prose declares, order-preserving, first-per-label. This is what makes
    the outcomes metric PER-REC: a rec that says "P2C1 (1.79→2.8)" carries
    its own current/target instead of inheriting the run-wide worst gap
    (the production uniform "P2C1 score 1.79 → 4.0 on every card" bug)."""
    out: list[dict] = []
    seen: set[str] = set()
    for m in _SCORE_TRANSITION_RE.finditer(text or ""):
        label = m.group(1)
        if label in seen:
            continue
        try:
            current, target = float(m.group(2)), float(m.group(3))
        except ValueError:
            continue
        # Maturity scores live on the 0-5 band; anything else is a
        # different quantity ("$2.4 → 3.1M") — never a score transition.
        if not (0.0 <= current <= 5.0 and 0.0 < target <= 5.0):
            continue
        seen.add(label)
        out.append({"label": label, "current": current, "target": target})
    return out


def mine_description_enrichment(
    *,
    title: str | None,
    description: str | None,
    effort_band: str | None = None,
    rec_id: str = "",
) -> dict:
    """048-field mining over PERSISTED rec text — the tier for rows whose
    rich source JSON is unavailable. E-IDs by citation regex, durations/
    metrics via nlp.quantities, peers via NER over the peer clauses,
    phase from the effort band. Honest None where the prose is silent."""
    text = f"{title or ''}\n{description or ''}"
    seen: set[str] = set()
    e_ids: list[str] = []
    for e in _E_ID_RE.findall(description or ""):
        if e not in seen:
            seen.add(e)
            e_ids.append(e)

    phase = _EFFORT_PHASE.get((effort_band or "").strip().upper())
    m = _DURATION_RE.search(description or "")
    time_txt = m.group(0).strip() if m else (_PHASE_WINDOW.get(phase) if phase else None)
    effort_txt = None
    if effort_band:
        up = effort_band.strip().upper()
        effort_txt = {"SMALL": "S", "MEDIUM": "M", "LARGE": "L", "XLARGE": "XL"}.get(up, up[:2])

    metric_txt = None
    # The rec's OWN declared maturity transition is THE outcomes metric —
    # per-rec by construction ("P2C1 (1.79→2.8)" ⇒ "P2C1 score 1.79 → 2.8").
    transitions = extract_score_transitions(f"{title or ''}\n{description or ''}")
    if transitions:
        t0 = transitions[0]
        metric_txt = compose_score_metric(
            t0["label"], t0["current"], target=t0["target"],
        )
    if not metric_txt:
        metrics = extract_metrics(description or "")
        if metrics:
            m0 = metrics[0]
            label = m0.get("metric") or "outcome"
            metric_txt = f"{label} {m0.get('raw') or m0.get('value')}".strip()[:160]
    if not metric_txt:
        sc = _SCORE_CLAUSE_RE.search(description or "")
        if sc:
            cat, cur, peer_med = sc.group(1), sc.group(2), sc.group(3)
            tgt = " → 4.0" if re.search(r"\bM4\b", description or "") else ""
            metric_txt = f"{cat} score {cur}{tgt}"
            if peer_med:
                metric_txt += f" (peer median {peer_med})"
            metric_txt = metric_txt[:160]
    if not metric_txt:
        # Verbatim maturity-score clause ("FCNCA scores 1.2 vs peer
        # median 3.0 (-1.76 gap)") — grounded, no reshaping.
        clause = re.search(
            r"[^.\n]*\bscores?\s+(?:lowest\s+at\s+)?\d(?:\.\d+)?[^.\n]*",
            description or "",
        )
        if clause:
            metric_txt = clause.group(0).strip()[:160]

    peer_txt = None
    peer_clause = _PEER_SENT_RE.search(description or "")
    if peer_clause:
        try:
            from app.services.nlp.entities import extract as ner_extract
            orgs = ner_extract(peer_clause.group(0)).get("orgs") or []
            if orgs:
                peer_txt = str(orgs[0].get("text") or "").strip()[:120] or None
        except Exception:
            peer_txt = None

    requires, prereq_of = extract_dependencies(
        {"cross_pillar_unlock": description or ""}, rec_id,
    )
    outcomes = {"time": time_txt, "effort": effort_txt,
                "metric": metric_txt, "peer": peer_txt}
    return {
        "feature": feature_from_text(text),
        "phase": phase,
        "root_cause_e_ids": e_ids[:12],
        "outcomes": outcomes if any(outcomes.values()) else None,
        "requires_rec_ids": requires,
        "prereq_of_rec_ids": prereq_of,
    }


def parse_rec_dir(dir_path: str | Path) -> list[dict]:
    """Parse a per-REC directory (`08_appendices/recommendations/REC-*.json`)
    into raw rec dicts, id-sorted. Malformed files are skipped — a bad rec
    file never aborts the package."""
    d = Path(dir_path)
    out: list[dict] = []
    if not d.is_dir():
        return out
    for p in sorted(d.glob("REC-*.json")):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(raw, dict):
            raw.setdefault("id", p.stem)
            out.append(raw)
    return out


def find_rec_sources(package_root: str | Path) -> list[Path]:
    """Locate every rec source in a package dir, richest first: per-REC
    directories, then the aggregate detail/register/export files."""
    root = Path(package_root)
    if not root.is_dir():
        return []
    sources: list[Path] = []
    per_rec = sorted(root.glob("**/recommendations/REC-*.json"))
    if per_rec:
        sources.append(per_rec[0].parent)
    for name in ("recommendations_detail.json", "recommendations_register.json",
                 "recommendations.json", "06_recommendations.json"):
        sources.extend(sorted(root.glob(f"**/{name}")))
    return sources
