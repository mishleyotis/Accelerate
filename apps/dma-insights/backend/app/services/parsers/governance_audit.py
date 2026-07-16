"""Parse bot governance audit logs (reasoning chain + contradictions).

Per the v2-QA under-leveraged matrix §C7 finding (2026-06-07), some
DMA packages ship audit logs that capture the bot's actual reasoning
chain and contradiction adjudication. Currently lost — D3 HeatmapPage
re-runs Vertex to synthesize a different rationale even though the
bot's analyst-validated reasoning is in the package.

Files handled:

  07_governance/reasoning_chain_log.json
      Shape: {run_id, version, subcap_chains: [...]}
      Each subcap_chain: {subcap_id, category, decision_path: [str], ...}
      Nicola_Wealth ships 12 subcap chains.

  07_governance/contradiction_log.csv
      Columns: contradiction_id, subcap_id, evidence_a_id,
               evidence_a_ers, evidence_a_claim, evidence_b_id,
               evidence_b_ers, evidence_b_claim, resolution_rule,
               winner, justification, confidence_impact,
               flagged_in_report, contradiction_type
      Nicola + Odlum_Brown both ship the file.

End-user impact: D6 Health "Audit" tab (Analyst-only) shows the bot's
actual reasoning chain + contradiction adjudication. Reviewer trust
gap closed — auditor can confirm the bot's logic aligns with the
final scoring without re-deriving from raw evidence.
"""
from __future__ import annotations

import contextlib
import csv
import json
import re
from io import StringIO
from pathlib import Path

from app.schemas.package import (
    ContradictionRow,
    GovernanceAuditLogs,
    ReasoningChainSubcap,
)

# CSV header-name aliases for the contradiction log. Both real fixtures
# (Nicola + Odlum) use the same column shape so the alias table is
# minimal; kept for future bot variants.
_CONTRA_ALIASES = {
    "contradiction_id": {"contradiction_id", "id", "contraid", "contra_id"},
    "subcap_id": {
        "subcap_id", "subcap", "category", "subcap_area", "affected_subcap",
        "affected_id", "capability_id",
    },
    "evidence_a_id": {
        "evidence_a_id", "evidencea_id", "ea_id", "a_id", "evidence_a",
        "positive_signal",
    },
    "evidence_b_id": {
        "evidence_b_id", "evidenceb_id", "eb_id", "b_id", "evidence_b",
        "negative_signal",
    },
    "winner": {"winner", "resolution_winner"},
    "justification": {"justification", "rationale", "reasoning"},
    "contradiction_type": {"contradiction_type", "type", "kind"},
}


def _build_idx(headers: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    norm = [h.lower().strip() for h in headers]
    for canonical, aliases in _CONTRA_ALIASES.items():
        for i, h in enumerate(norm):
            if h in aliases:
                out[canonical] = i
                break
    return out


_SUBCAP_PREFIX_RE = re.compile(r"P\d+C\d+(?:\.\d+)*")


def _parse_key_decisions(items: list) -> list[ReasoningChainSubcap]:
    """Map the `key_decisions` reasoning-log variant onto
    ReasoningChainSubcap rows."""
    out: list[ReasoningChainSubcap] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        raw_subcap = str(entry.get("subcap") or entry.get("subcap_id") or "").strip()
        if not raw_subcap:
            continue
        m = _SUBCAP_PREFIX_RE.search(raw_subcap)
        subcap_id = m.group(0) if m else raw_subcap[:32]
        # Build a one-line decision step from the available fields.
        step = " — ".join(filter(None, (
            str(entry.get("decision") or "").strip() or None,
            str(entry.get("evidence") or "").strip() or None,
        )))
        decision_path = [step] if step else []
        kwargs: dict = {
            "subcap_id": subcap_id,
            "category": m.group(0) if m else None,
            "decision_path": decision_path,
        }
        for k in ("ceiling", "caps", "confidence", "decision", "evidence"):
            v = entry.get(k)
            if v is not None:
                kwargs[k] = v
        if raw_subcap != subcap_id:
            kwargs["raw_subcap"] = raw_subcap
        with contextlib.suppress(Exception):
            out.append(ReasoningChainSubcap(**kwargs))
    return out


# Top-level keys under which the corpus nests the chain list (the same
# rows under many different names: chains / sample_chains / reasoning_chains
# / subcaps / …). Tried in order; first non-empty wins.
_CHAIN_LIST_KEYS = (
    "subcap_chains", "chains", "chain", "reasoning_chains",
    "reasoning_chain_entries", "sample_chains", "sample_chain", "subcaps",
)


def _split_decision_path(v: object) -> list[str]:
    """decision_path is a list of steps (Nicola) OR an arrow-joined string
    ('evidence → ceiling → caps → final'). Normalise both to a list."""
    if isinstance(v, list):
        return [str(s).strip() for s in v if str(s).strip()]
    if isinstance(v, str):
        parts = re.split(r"→|->|;|→|\|", v)
        return [p.strip() for p in parts if p.strip()]
    return []


def _ci_get(d: dict, *keys: str) -> object:
    """Case/underscore-insensitive lookup across candidate keys — corpus
    reasoning logs use SubCap_ID / subcap_id / id / subcap interchangeably."""
    norm = {str(k).lower().replace("_", ""): v for k, v in d.items()}
    for key in keys:
        v = norm.get(key.lower().replace("_", ""))
        if v not in (None, ""):
            return v
    return None


def _row_from_chain_entry(subcap_id: object, entry: dict) -> ReasoningChainSubcap | None:
    sid = str(subcap_id or "").strip()
    if not sid:
        return None
    m = _SUBCAP_PREFIX_RE.search(sid)
    dp = _ci_get(entry, "decision_path", "decision")
    kwargs: dict = {
        "subcap_id": sid[:64],
        "category": (
            str(entry.get("category") or entry.get("category_id")).strip()
            if (entry.get("category") or entry.get("category_id")) is not None
            else (m.group(0) if m else None)
        ),
        "decision_path": _split_decision_path(dp),
    }
    for k, v in entry.items():
        if k in ("subcap_id", "subcap", "category", "category_id", "decision_path"):
            continue
        if v is not None:
            kwargs[k] = v
    with contextlib.suppress(Exception):
        return ReasoningChainSubcap(**kwargs)
    return None


def parse_reasoning_chain(path: Path) -> list[ReasoningChainSubcap]:
    """Parse `reasoning_chain_log.json` into typed rows.

    Schema-tolerant across the corpus variants: a list of chain dicts under
    any of `_CHAIN_LIST_KEYS`; the `key_decisions` flat shape; or a dict
    keyed directly by subcap id (`{"P1C1.1.1": {decision_path, …}}`).
    Returns [] for missing file / malformed JSON / no recognizable chain.
    """
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    # Top-level list of chain dicts (Security Finance ships the chain as a
    # bare JSON array).
    if isinstance(data, list):
        rows = [
            _row_from_chain_entry(_ci_get(e, "subcap_id", "subcap", "id"), e)
            for e in data if isinstance(e, dict)
        ]
        return [r for r in rows if r is not None]
    if not isinstance(data, dict):
        return []

    # 1. Chain entries under any known key — as a LIST of dicts, OR as a
    #    DICT keyed by subcap id (Corporate America nests `subcaps` as
    #    {"P1C1.1.1": {final_score, …}}).
    for key in _CHAIN_LIST_KEYS:
        val = data.get(key)
        rows: list[ReasoningChainSubcap] = []
        if isinstance(val, list) and val:
            rows = [
                _row_from_chain_entry(
                    _ci_get(e, "subcap_id", "subcap", "id"), e)
                for e in val if isinstance(e, dict)
            ]
        elif isinstance(val, dict) and val:
            rows = [
                _row_from_chain_entry(k, v) for k, v in val.items()
                if isinstance(v, dict) and re.match(r"^P\d+C\d+", str(k))
            ]
        rows = [r for r in rows if r is not None]
        if rows:
            return rows

    # 2. The `key_decisions` flat shape (subcap/decision/evidence/ceiling).
    if isinstance(data.get("key_decisions"), list):
        rows = _parse_key_decisions(data["key_decisions"])
        if rows:
            return rows

    # 3. A dict keyed directly by subcap id.
    keyed = [
        (k, v) for k, v in data.items()
        if isinstance(v, dict) and re.match(r"^P\d+C\d+", str(k))
    ]
    if keyed:
        rows = [_row_from_chain_entry(k, v) for k, v in keyed]
        rows = [r for r in rows if r is not None]
        if rows:
            return rows
    return []


def parse_contradictions(path: Path) -> list[ContradictionRow]:
    """Parse `contradiction_log.csv` into typed rows.

    Returns [] for missing file / empty file / header mismatch.
    """
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if not raw.strip():
        return []
    # Skip leading `#` comment / blank banner lines (Empower ships a
    # "# RUN_ID: …" line before the header) so DictReader anchors on the
    # real header.
    raw = "\n".join(
        ln for ln in raw.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    )
    if not raw.strip():
        return []
    reader = csv.reader(StringIO(raw))
    try:
        headers = next(reader)
    except StopIteration:
        return []
    idx = _build_idx(headers)
    # Need at least a subcap or contradiction anchor; synthesise the id when
    # the variant ships only a subcap column (LPL / American Homes).
    if "contradiction_id" not in idx and "subcap_id" not in idx:
        return []
    out: list[ContradictionRow] = []
    for i, row in enumerate(reader):
        if not row or not any(c.strip() for c in row):
            continue

        def cell(field: str, _row: list[str] = row) -> str | None:
            i = idx.get(field)
            if i is None or i >= len(_row):
                return None
            v = _row[i].strip()
            return v or None

        cid = cell("contradiction_id") or f"CONTRA-{i + 1:03d}"
        kwargs = {
            "contradiction_id": cid[:64],
            "subcap_id": cell("subcap_id"),
            "evidence_a_id": cell("evidence_a_id"),
            "evidence_b_id": cell("evidence_b_id"),
            "winner": cell("winner"),
            "justification": cell("justification"),
            "contradiction_type": cell("contradiction_type"),
        }
        # Preserve extras (evidence_a_ers, claim, resolution_rule,
        # confidence_impact, etc.) by walking the original headers.
        norm = [h.lower().strip() for h in headers]
        for i, h in enumerate(norm):
            if i >= len(row):
                continue
            if h in {a for aliases in _CONTRA_ALIASES.values() for a in aliases}:
                continue
            v = row[i].strip()
            if v:
                kwargs[h] = v
        with contextlib.suppress(Exception):
            out.append(ContradictionRow(**kwargs))
    return out


def parse_governance_audit_logs(root_p: Path) -> GovernanceAuditLogs | None:
    """Top-level entrypoint. Sweeps the package for the audit logs and
    aggregates into a single envelope.

    The logs land in several folders across the corpus — 07_governance
    (canonical), but also 03_scoring_workbook, 08_appendices, 01_evidence,
    and the capital-G `04_Governance` variant — so we search RECURSIVELY
    within the resolved root rather than only 07_governance (which missed
    ~22 packages shipping contradiction_log.csv elsewhere). First non-empty
    source wins for each log (copies in multiple folders are duplicates,
    not additions).

    Returns None when no audit files were found (parser_warnings is not
    emitted in that case — silence is the correct signal that the package
    is governance-light).
    """
    chains: list[ReasoningChainSubcap] = []
    for chain_path in (
        *sorted(root_p.glob("**/reasoning_chain_log.json")),
        *sorted(root_p.glob("**/reasoning_*log*.json")),
    ):
        chains = parse_reasoning_chain(chain_path)
        if chains:
            break

    contras: list[ContradictionRow] = []
    for contra_path in sorted(root_p.glob("**/contradiction_log.csv")):
        contras = parse_contradictions(contra_path)
        if contras:
            break

    if not chains and not contras:
        return None
    return GovernanceAuditLogs(
        reasoning_chain=chains,
        contradictions=contras,
    )
