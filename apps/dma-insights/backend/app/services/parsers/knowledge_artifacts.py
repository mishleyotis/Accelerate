"""Unconsumed-artifact knowledge mining — the client knowledge array feeder.

Part 12.5/12.6: the consumed layer (scoring CSVs, evidence, peers,
governance, reports) is healthy; the analyst-judgment layer
(zennify opportunities, uncertainty registers, org-capability proxies)
and every future new artifact shape were dropped on the floor. This
module walks a parsed package AFTER the existing parsers ran and:

  1. runs the registered fingerprint parsers over MATERIAL artifacts
     the pipeline doesn't already consume
     (``zennify_opportunities`` / ``uncertainty_register`` /
     ``org_capability`` — matched via ``nlp.patterns`` header/key
     fingerprints, not filenames);
  2. falls to the generic section miner for MATERIAL text artifacts
     that match no fingerprint, recording a ``nlp.patterns``
     pattern_gap per unmatched shape (the registry's learning signal);
  3. returns a ``PackageKnowledge`` envelope the backfill persists into
     ``client_knowledge_sections`` (+ ``runs.uncertainty_bands``).

Mining is best-effort per artifact: a corrupt file yields a DEGRADED
warning and the walk continues (per-file quarantine semantics).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from app.services.artifact_manifest import COSMETIC, classify_path
from app.services.nlp import patterns
from app.services.parsers import org_capability as _org
from app.services.parsers import uncertainty_register as _unc
from app.services.parsers import zennify_opportunities as _opp
from app.services.parsers.section_miner import mine_generic

log = structlog.get_logger()

# Artifacts the EXISTING pipeline already consumes — the miner must not
# double-ingest them (their content lives in the domain tables). Matched
# case-insensitively against the package-relative POSIX path.
_CONSUMED_RES: tuple[re.Pattern[str], ...] = tuple(re.compile(p, re.I) for p in (
    r"(^|/)manifest\.json$",
    r"run_manifest.*\.json$",
    r"verdict.*\.json$",
    r"audit_summary\.json$",
    r"evidence_index",                  # incl. A1_Evidence_Index variants
    r"evidence_inventory",              # duplicates evidence_index content
    r"evidence_master",                 # ditto (merged evidence twin)
    r"merged_evidence",
    r"evidence_ers_ranking",
    # Documented exclusions (ARTIFACT_COVERAGE.md): audit search logs are
    # optional provenance, scoring scratchpads are recomputable.
    r"search_log",
    r"proxy_search",
    r"scoring_scratchpad",
    r"evidence_summary",
    r"research_handoff",
    r"export_.*\.csv$",
    r"final_scores\.json$",
    r"peer_scores_.*\.json$",
    r"peer_comparison_table\.csv$",
    r"peer_benchmarks\.json$",
    r"issue_register.*\.(csv|json)$",
    r"recommendations?_(detail|register)\.json$",
    r"recommendation_validation\.json$",
    r"caps_applied_log\.csv$",
    r"contradiction_log\.csv$",
    r"reasoning_chain_log\.json$",
    r"assumptions?_register",
    r"section_analysis_\d+\.json$",
    r"report_synthesis\.md$",
    r"entity_profile\.json$",
    r"(^|/|_)00_parameters\.json$|assessment_parameters\.json$",
    r"financial_trends\.csv$",
    r"financial_baseline\.json$",
    r"sentiment_data\.csv$",
    r"tech_?stack",
    r"04_reports/.*\.docx$",            # assessment/client-profile parsers
    # Report DOCX shipped OUTSIDE 04_reports (GESA roots them) is still
    # consumed by find_assessment_reports / client_profile globs.
    r"(assessment_report|client_profile).*\.docx$",
    r"subcap_taxonomy\.json$",
))

# Suffixes the miner can extract text from. Workbooks (xlsx) are handled
# by the scoring path and skipped here (documented exclusion).
_MINEABLE_SUFFIXES = frozenset({".csv", ".tsv", ".json", ".md", ".txt", ".docx"})

# Package-level ceiling on generic sections so a row-heavy appendix
# can't flood the knowledge table (per-artifact cap lives in
# section_miner.MAX_SECTIONS_PER_ARTIFACT).
MAX_GENERIC_SECTIONS_PER_PACKAGE = 400

_SPECIFIC_PARSERS: dict[str, Any] = {}


def register_all() -> None:
    """Idempotent registration of every knowledge-artifact fingerprint."""
    _opp.register_fingerprints()
    _unc.register_fingerprints()
    _org.register_fingerprints()
    _SPECIFIC_PARSERS[_opp.PARSER_KEY] = _opp
    _SPECIFIC_PARSERS[_unc.PARSER_KEY] = _unc
    _SPECIFIC_PARSERS[_org.PARSER_KEY] = _org


@dataclass
class PackageKnowledge:
    """Everything the knowledge miner extracted from one package."""

    sections: list[dict] = field(default_factory=list)
    uncertainty_bands: list[dict] = field(default_factory=list)
    pattern_gaps: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def _is_consumed(rel: str) -> bool:
    return any(rx.search(rel) for rx in _CONSUMED_RES)


def _peek_headers_keys(
    path: Path,
) -> tuple[list[str] | None, list[str] | None]:
    """Cheap structural peek: CSV header row / JSON top-level keys."""
    suffix = path.suffix.lower()
    try:
        if suffix in (".csv", ".tsv"):
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.strip() and not line.lstrip().startswith("#"):
                        headers = next(
                            csv.reader(io.StringIO(line)), [],
                        )
                        return (
                            [re.sub(r"\s+", "_", h.strip().lower())
                             for h in headers],
                            None,
                        )
            return [], None
        if suffix == ".json":
            if path.stat().st_size > 4 * 1024 * 1024:
                return None, []
            data = json.loads(
                path.read_text(encoding="utf-8", errors="replace")
            )
            if isinstance(data, dict):
                return None, [str(k) for k in data][:64]
            return None, []
    except Exception:
        return None, None
    return None, None


def _sha256_file(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def mine_package_knowledge(
    root_p: Path, warnings: list[str],
) -> PackageKnowledge:
    """Mine every unconsumed MATERIAL artifact under ``root_p``.

    Appends severity-prefixed strings to ``warnings`` (DEGRADED per
    mining failure, one INFO pattern_gap note per unmatched shape) and
    returns the ``PackageKnowledge`` envelope for the persist stage.
    """
    register_all()
    knowledge = PackageKnowledge()
    counts: dict[str, int] = {}
    generic_budget = MAX_GENERIC_SECTIONS_PER_PACKAGE

    for f in sorted(root_p.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in _MINEABLE_SUFFIXES:
            continue
        try:
            rel = f.relative_to(root_p).as_posix()
        except ValueError:
            continue
        if classify_path(rel) == COSMETIC or _is_consumed(rel):
            continue

        headers, keys = _peek_headers_keys(f)
        parser_key, confidence = patterns.match_artifact(
            f, headers=headers, keys=keys,
        )
        try:
            if parser_key == _opp.PARSER_KEY:
                sections = _opp.parse_opportunities(f, rel)
            elif parser_key == _unc.PARSER_KEY:
                sections, bands = _unc.parse_uncertainty(f, rel)
                knowledge.uncertainty_bands.extend(bands)
            elif parser_key == _org.PARSER_KEY:
                sections = _org.parse_org_capability(f, rel)
            elif parser_key is not None:
                # Another module's registered fingerprint owns this
                # shape — it is consumed elsewhere; skip silently.
                continue
            else:
                # Fallback rung: generic mining + pattern-gap learning
                # signal (Part 2 report-agnosticism contract).
                if generic_budget <= 0:
                    continue
                sections = mine_generic(f, rel)[:generic_budget]
                generic_budget -= len(sections)
                if sections:
                    gap = patterns.record_pattern_gap(
                        knowledge.pattern_gaps, rel,
                        reason=(
                            f"no fingerprint matched (best confidence "
                            f"{confidence:.2f}); {len(sections)} generic "
                            f"sections mined"
                        ),
                    )
                    warnings.append(
                        f"INFO/pattern_gap: {gap['path']} — {gap['reason']}"
                    )
        except Exception as e:
            # Per-file quarantine: one bad artifact never aborts the
            # package (nor the rest of the mining walk).
            warnings.append(
                f"DEGRADED/knowledge_artifact_failed: {rel} "
                f"({type(e).__name__}: {str(e)[:160]})"
            )
            continue

        if not sections:
            continue
        sha = _sha256_file(f)
        for s in sections:
            s["sha256"] = sha
        knowledge.sections.extend(sections)
        kind = sections[0].get("artifact_kind", "generic")
        counts[kind] = counts.get(kind, 0) + len(sections)

    knowledge.stats = {
        "sections_by_kind": counts,
        "pattern_gaps": len(knowledge.pattern_gaps),
        "uncertainty_bands": len(knowledge.uncertainty_bands),
    }
    if knowledge.sections:
        log.info(
            "knowledge_artifacts.mined",
            root=str(root_p),
            **{f"kind_{k}": v for k, v in counts.items()},
            pattern_gaps=len(knowledge.pattern_gaps),
        )
    return knowledge


_INSERT_SECTIONS_SQL = """
    INSERT INTO client_knowledge_sections (
        entity_id, run_id, artifact_kind, source_path, sha256,
        heading, body, page, provenance
    ) VALUES (
        CAST(:eid AS uuid), CAST(:rid AS uuid), :kind, :sp, :sha,
        :heading, :body, :page, CAST(:prov AS JSONB)
    )
"""


async def persist_knowledge(
    session: Any,
    *,
    entity_id: str,
    run_id: str,
    knowledge: PackageKnowledge,
) -> dict[str, int]:
    """Persist mined sections idempotently (DELETE-then-INSERT per run)
    and populate ``runs.uncertainty_bands`` when the column is empty.

    Batched: one DELETE + one executemany INSERT + one conditional
    UPDATE — never one round-trip per section.
    """
    from sqlalchemy import text

    await session.execute(
        text(
            "DELETE FROM client_knowledge_sections "
            "WHERE run_id = CAST(:rid AS uuid)"
        ),
        {"rid": str(run_id)},
    )
    rows = [
        {
            "eid": str(entity_id),
            "rid": str(run_id),
            "kind": str(s.get("artifact_kind") or "generic")[:48],
            "sp": str(s.get("source_path") or "(unknown)"),
            "sha": (s.get("sha256") or None),
            "heading": (s.get("heading") or None),
            "body": str(s.get("body") or ""),
            "page": s.get("page"),
            "prov": json.dumps(s.get("provenance") or {}, ensure_ascii=False),
        }
        for s in knowledge.sections
        if (s.get("body") or "").strip()
    ]
    if rows:
        await session.execute(text(_INSERT_SECTIONS_SQL), rows)

    bands_written = 0
    if knowledge.uncertainty_bands:
        result = await session.execute(
            text(
                "UPDATE runs SET uncertainty_bands = CAST(:b AS JSONB) "
                "WHERE id = CAST(:rid AS uuid) "
                "  AND (uncertainty_bands IS NULL "
                "       OR uncertainty_bands = 'null'::jsonb "
                "       OR uncertainty_bands = '[]'::jsonb "
                "       OR uncertainty_bands = '{}'::jsonb)"
            ),
            {
                "b": json.dumps(knowledge.uncertainty_bands),
                "rid": str(run_id),
            },
        )
        bands_written = int(result.rowcount or 0)

    return {
        "sections_inserted": len(rows),
        "uncertainty_bands_written": bands_written,
    }
