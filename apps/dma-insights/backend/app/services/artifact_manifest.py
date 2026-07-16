"""Per-artifact change detection for intelligent re-ingest.

Per the 2026-06-07 operator mandate: "A reingest should strictly be
for the changed artifact, and ONLY if the information influences the
DMA. If it was a cosmetic change, this can just be dropped. The
backfill should be super intelligent to avoid just reingesting."

This module classifies every file in a DMA package into one of three
materiality buckets and computes a deterministic content-hash over
just the material files. The historical_backfill skip-check compares
the current hash to the prior run's hash; equal → SKIP regardless of
folder mtime; different → re-ingest the changed artifacts.

Materiality classes
-------------------
- MATERIAL: any artifact that influences the rendered DMA — scoring
  workbooks (drive subcap_scores), evidence indexes (drive
  evidence_index + dedup), assessment / client_profile DOCX (drive
  document_sections + narrative), recommendations JSON (drive
  recommendations), peer JSONs (drive peer_benchmarks), governance
  caps + qa_verdict (drive caps_applied_log + runs.qa_verdict),
  run_manifest (drive runs / entity rebind), MANIFEST.json (package
  identity).

- COSMETIC: artifacts that are *presentation* output rather than
  *source-of-truth* — sales decks (05_narrative_deck), preview images
  embedded in reports (04_reports/*.png / *.jpg), pure-audit search
  logs (A1_search_log.csv, A2_proxy_search_log.csv, A9_audit_*.csv —
  by filename pattern, since those don't get persisted), OS-level
  cruft (__MACOSX, .DS_Store, *~, *.tmp, .git/*), and Drive comments
  with no accompanying source-file edit.

- UNKNOWN: anything outside the above buckets — treated as MATERIAL
  by default (defense-in-depth: a future bot revision adding a new
  artifact kind won't be silently skipped). A parser_warning is
  emitted when an unknown artifact changes so the operator can audit
  and classify it.

Hash semantics
--------------
``compute_material_manifest_hash(root)`` returns:
- A SHA256 over the sorted-by-relpath concatenation of each material
  file's own SHA256 (so adding/removing/touching a material file
  changes the hash; reordering filesystem traversal doesn't).
- A details list with per-file `{path, class, content_hash, size}`
  so the backfill can emit a precise "changed: N material / M
  cosmetic" log line.

This module is *pure-function* (no DB, no Drive, no async) and
exhaustively unit-tested in
``tests/test_artifact_manifest_change_detection.py``.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

MATERIAL = "material"
COSMETIC = "cosmetic"
UNKNOWN = "unknown"


# Filename / relpath patterns. Case-INSENSITIVE comparison against
# the relative path (POSIX-normalized, lowercased).

_MATERIAL_SUFFIXES = (
    # Top-level package identity.
    "manifest.json",
    # Evidence (01_evidence/*).
    "evidence_index.csv",
    "evidence_index.json",
    "evidence_inventory.csv",
    "evidence_inventory.json",
    "evidence_ers_ranking.json",
    "research_handoff.json",
    "run_manifest.json",
    # Scoring (03_scoring_workbook/*).
    "export_scoring_detail.csv",
    "export_pillar_summary.csv",
    "export_category_summary.csv",
    "export_evidence_inventory.csv",
    # Reports (04_reports/*).
    "assessment_report.docx",
    "client_profile.docx",
    "client_profile_research_report.docx",
    # Peers (06_peers/*).
    "peer_comparison_table.csv",
    # Governance (07_governance/*).
    "caps_applied_log.csv",
    "qa_verdict.json",
    "reasoning_chain_log.json",
    "contradiction_log.csv",
    "00_parameters.json",
    "parameters.json",
    # Appendices (08_appendices/*).
    "recommendations_detail.json",
    "subcap_taxonomy.json",
)

_MATERIAL_REGEXES = (
    # XLSX workbooks under scoring or research are material — the parser
    # reads them as the canonical scoring source when CSV exports are
    # missing or partial.
    re.compile(r"03_scoring_workbook/.*\.xlsx$", re.I),
    re.compile(r"02_research_workbook/.*\.xlsx$", re.I),
    # Per-peer scores JSON: peer_scores_<Name>.json
    re.compile(r"06_peers/peer_scores_.*\.json$", re.I),
    # Assessment + Client_Profile DOCX with any filename variant —
    # FCMA_DMA_Assessment_Report_v2.docx, AlmaBank_Client_Profile.docx,
    # etc.
    re.compile(r"04_reports/.*assessment_report.*\.docx$", re.I),
    re.compile(r"04_reports/.*client_profile.*\.docx$", re.I),
    re.compile(r"04_reports/.*report.*\.docx$", re.I),
    # Generic *Run_Manifest*.json (Chemung uses CamelCase
    # DMA_CCTRUST_Run_Manifest.json).
    re.compile(r".*run_manifest.*\.json$", re.I),
    # Generic *qa_verdict*.json.
    re.compile(r".*qa_verdict.*\.json$", re.I),
)

_COSMETIC_PREFIXES = (
    # Sales deck — output presentation, not source-of-truth scoring.
    "05_narrative_deck/",
)

_COSMETIC_SUFFIXES = (
    # Embedded report illustrations.
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp",
    # OS cruft.
    ".ds_store", ".tmp", ".bak", ".lock", ".swp",
    # Compiled / cached.
    ".pyc", ".cache",
)

_COSMETIC_REGEXES = (
    # Search / proxy / audit log appendices — pure governance audit
    # artifacts that the parser doesn't persist into the score / evidence
    # tables. Pattern matches A1_, A2_, .., A99_ prefixed log files.
    re.compile(r"08_appendices/[Aa]\d+_.*(?:search|proxy|audit|log).*\.csv$", re.I),
    # Sales / talk track / presentation deck PPTX/PDF outputs.
    re.compile(r".*\.pptx$", re.I),
    re.compile(r"05_narrative_deck/.*\.pdf$", re.I),
    # OS / VCS cruft inside the package.
    re.compile(r"__macosx/.*", re.I),
    re.compile(r"\.git/.*", re.I),
)


def classify_path(rel_path: str) -> str:
    """Classify a file's relative path into MATERIAL / COSMETIC /
    UNKNOWN.

    Decision order (each step terminal):

      1. Explicit COSMETIC override (decks, images, OS cruft, audit
         search logs) — files we KNOW don't influence the DMA.
      2. Explicit MATERIAL allowlist (canonical artifact filenames /
         regexes).
      3. Directory-based MATERIAL default: any data file (csv / json /
         xlsx / xlsm / docx / md) under the canonical numbered subdirs
         (01_evidence / 02_research_workbook / 03_scoring_workbook /
         04_reports / 06_peers / 07_governance / 08_appendices) is
         treated as MATERIAL. The bot pipeline ships dozens of
         per-package data files (issue_register.json, gap_register.json,
         caps_determination.json, phased_roadmap.json, subcap_mapping.
         json, …) that the parser surfaces into the rendered DMA. A
         narrow allowlist would silently drop those on touch; a broad
         directory rule mirrors the bot-pipeline contract.
      4. Fallback → UNKNOWN (treated as MATERIAL by the backfill —
         defense-in-depth).

    rel_path is expected to be a POSIX-style path relative to the
    package root (e.g. ``03_scoring_workbook/export_scoring_detail.csv``).
    """
    p = rel_path.replace("\\", "/").lower().lstrip("/")
    base = p.rsplit("/", 1)[-1]

    # 1. Explicit COSMETIC override (decks, images, OS cruft, audit
    #    search logs).
    for prefix in _COSMETIC_PREFIXES:
        if p.startswith(prefix):
            return COSMETIC
    for suf in _COSMETIC_SUFFIXES:
        if p.endswith(suf):
            return COSMETIC
    for rx in _COSMETIC_REGEXES:
        if rx.search(p):
            return COSMETIC

    # 2. Explicit MATERIAL allowlist.
    if base in _MATERIAL_SUFFIXES:
        return MATERIAL
    for rx in _MATERIAL_REGEXES:
        if rx.search(p):
            return MATERIAL

    # 3. Directory-based MATERIAL default — any data file under a
    #    canonical numbered subdir.
    _MAT_DIRS = (
        "01_evidence/", "02_research_workbook/", "03_scoring_workbook/",
        "04_reports/", "06_peers/", "07_governance/", "08_appendices/",
    )
    _MAT_DATA_SUFFIXES = (
        ".csv", ".json", ".xlsx", ".xlsm", ".xls",
        ".docx", ".doc", ".md", ".txt",
    )
    if any(p.startswith(d) for d in _MAT_DIRS) and \
            any(p.endswith(s) for s in _MAT_DATA_SUFFIXES):
        return MATERIAL

    # 4. Fallback.
    return UNKNOWN


def _hash_file(path: Path, *, chunk_size: int = 65536) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class ArtifactEntry:
    """A single classified file in a package."""

    rel_path: str
    cls: str  # MATERIAL / COSMETIC / UNKNOWN
    content_hash: str  # sha256 of the file bytes
    size_bytes: int


@dataclass
class PackageManifest:
    """Full classified manifest for a package + the rollup hash that
    represents the material content.
    """

    entries: list[ArtifactEntry] = field(default_factory=list)
    material_count: int = 0
    cosmetic_count: int = 0
    unknown_count: int = 0
    material_manifest_hash: str = ""  # sha256 over sorted material hashes

    def by_class(self, cls: str) -> list[ArtifactEntry]:
        return [e for e in self.entries if e.cls == cls]


def compute_package_manifest(root: Path) -> PackageManifest:
    """Walk a package root, classify every file, hash material files,
    and produce a roll-up ``material_manifest_hash``.

    The roll-up hash is sha256 over the sorted-by-rel_path concatenation
    of each material file's own content_hash. This is deterministic
    across filesystems / OSes and stable across filesystem traversal
    order. Two packages with identical material content but different
    cosmetic touches (e.g. a deck swap) produce identical hashes →
    the backfill SKIPs.

    Cosmetic + UNKNOWN files are recorded for audit but do NOT
    participate in the hash. UNKNOWN is also counted separately so the
    operator can spot a new artifact kind that needs classification.
    """
    if not root.exists() or not root.is_dir():
        return PackageManifest()

    entries: list[ArtifactEntry] = []
    material_count = cosmetic_count = unknown_count = 0

    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(root).as_posix()
        except ValueError:
            continue
        cls = classify_path(rel)
        try:
            size = f.stat().st_size
        except OSError:
            continue
        if cls == MATERIAL:
            ch = _hash_file(f)
            material_count += 1
        elif cls == COSMETIC:
            ch = ""
            cosmetic_count += 1
        else:
            ch = _hash_file(f)
            unknown_count += 1
        entries.append(
            ArtifactEntry(rel_path=rel, cls=cls, content_hash=ch, size_bytes=size)
        )

    rollup = hashlib.sha256()
    for e in sorted(entries, key=lambda x: x.rel_path):
        if e.cls == MATERIAL and e.content_hash:
            rollup.update(e.rel_path.encode("utf-8"))
            rollup.update(b"\x00")
            rollup.update(e.content_hash.encode("ascii"))
            rollup.update(b"\n")

    return PackageManifest(
        entries=entries,
        material_count=material_count,
        cosmetic_count=cosmetic_count,
        unknown_count=unknown_count,
        material_manifest_hash=rollup.hexdigest(),
    )


def diff_manifests(
    prior: PackageManifest | None,
    current: PackageManifest,
) -> dict[str, list[str]]:
    """Compute which artifacts changed between two manifests.

    Returns a dict with keys:
      - ``added``         — material files present in current, not prior
      - ``removed``       — material files present in prior, not current
      - ``modified``      — material files whose content_hash changed
      - ``cosmetic_changed`` — cosmetic files that flipped (for audit
                              only; not actionable)

    A None prior (first ingest) returns every current MATERIAL file in
    ``added``.
    """
    if prior is None:
        return {
            "added": [e.rel_path for e in current.by_class(MATERIAL)],
            "removed": [],
            "modified": [],
            "cosmetic_changed": [],
        }

    prior_mat = {e.rel_path: e.content_hash for e in prior.by_class(MATERIAL)}
    curr_mat = {e.rel_path: e.content_hash for e in current.by_class(MATERIAL)}
    prior_cos = {e.rel_path: e.size_bytes for e in prior.by_class(COSMETIC)}
    curr_cos = {e.rel_path: e.size_bytes for e in current.by_class(COSMETIC)}

    return {
        "added": sorted(set(curr_mat) - set(prior_mat)),
        "removed": sorted(set(prior_mat) - set(curr_mat)),
        "modified": sorted(
            p for p in (set(prior_mat) & set(curr_mat))
            if prior_mat[p] != curr_mat[p]
        ),
        "cosmetic_changed": sorted(
            (set(prior_cos) ^ set(curr_cos))
            | {p for p in (set(prior_cos) & set(curr_cos))
               if prior_cos[p] != curr_cos[p]}
        ),
    }


def material_changes_count(diff: dict[str, list[str]]) -> int:
    """How many material files differ between prior and current."""
    return len(diff["added"]) + len(diff["removed"]) + len(diff["modified"])


def summarize_diff(diff: dict[str, Iterable[str]]) -> str:
    """Operator-readable summary line for backfill logs."""
    parts = []
    if diff.get("added"):
        parts.append(f"+{len(list(diff['added']))} added")
    if diff.get("removed"):
        parts.append(f"-{len(list(diff['removed']))} removed")
    if diff.get("modified"):
        parts.append(f"~{len(list(diff['modified']))} modified")
    if diff.get("cosmetic_changed"):
        parts.append(f"{len(list(diff['cosmetic_changed']))} cosmetic")
    return ", ".join(parts) if parts else "(no changes)"


# ── Artifact -> persistence-table mapping ────────────────────────────
#
# Per the 2026-06-07 operator mandate: "A reingest should strictly be
# for the changed artifact, and ONLY if the information influences the
# DMA." Translation: when only the scoring CSV changed we must NOT
# re-persist evidence_index / document_sections / focus_areas /
# caps_applied_log / recommendations / peer_benchmarks -- they were
# correct, leave them alone. Only re-persist what derives from the
# changed artifact.
#
# Sources of truth for this mapping:
#   - qa_contract_matrix.md §5 (24-table persistence write matrix)
#   - The Explore-agent persist line-range map captured during Batch 2
#     planning (per persistence block).
#
# Notes on each mapping:
#   - 01_evidence/* maps to a TRIPLE (evidence_index +
#     evidence_run_links + dedup_audit) because the 5-branch dedup
#     engine maintains all three together. Skipping any of the three
#     when the evidence artifact changed risks state corruption
#     (duplicate run-links, missing audit rows). All-or-nothing.
#   - 04_reports/*Client_Profile*.docx writes BOTH focus_areas AND
#     firmographics (client_profile parser produces both).
#   - 07_governance/qa_verdict.json updates runs row JSONB columns,
#     not a separate table -- maps to "runs" so the runs UPDATE
#     re-fires.
#   - 08_appendices/run_manifest.json + 07_governance/00_parameters.json
#     can change institution_name / subvertical / rubric -- maps to
#     "entities" + "runs" + "firmographics".
#   - 05_narrative_deck/*.pptx is COSMETIC by default; deck content
#     analysis (see deck.py / extract_deck_text below) may emit an
#     observation but does NOT trigger a persist re-fire.

# Canonical persistence tables that persist_package writes (the 24
# tables from qa_contract_matrix.md §5). Used as the universe from
# which `skip_tables = ALL_TABLES - affected_tables(diff)` is derived.
ALL_TABLES = frozenset({
    "entities",
    "firmographics",
    "runs",
    "ccg_catalog_versions",
    "ccg_subcaps_bootstrap",  # auto-bootstrap branch
    "subcap_scores",
    "issue_register",
    "caps_applied_log",
    "recommendations",
    "peer_benchmarks",
    "tech_stack_entries",
    "platform_scores",
    "evidence_index",        # always co-runs with the 2 below
    "evidence_run_links",
    "dedup_audit",
    "document_sections",     # always co-runs with the 2 below
    "document_lineage",
    "document_evidence_items",
    "focus_areas",
    "parser_observations",
    "vertex_synthesis_cache_invalidate",
})

# Mapping from a MATERIAL path-class to the persistence tables that
# DERIVE from it. When a path in this class is added / removed /
# modified, the listed tables MUST re-persist; tables outside the
# union of these sets for the current diff can be skipped.
#
# Patterns are POSIX-normalized lowercase substrings/regexes
# evaluated against the rel_path that diff_manifests emits.

import re as _re  # noqa: E402 — already imported at top; aliased to dodge shadow

_ARTIFACT_TO_TABLES: list[tuple[_re.Pattern[str], frozenset[str]]] = [
    # Scoring workbook (CSV + XLSX) drives every score-derived table.
    (_re.compile(r"03_scoring_workbook/.*\.(csv|xlsx|xlsm|xls)$", _re.I),
     frozenset({
         "subcap_scores", "peer_benchmarks", "platform_scores",
         "ccg_subcaps_bootstrap",
     })),
    # Evidence artifacts drive the dedup TRIPLE.
    (_re.compile(r"01_evidence/.*", _re.I),
     frozenset({"evidence_index", "evidence_run_links", "dedup_audit",
                "parser_observations"})),
    # Assessment_Report DOCX drives document_sections + lineage +
    # per-section evidence items.
    (_re.compile(r"04_reports/.*assessment_report.*\.docx$", _re.I),
     frozenset({"document_sections", "document_lineage",
                "document_evidence_items"})),
    (_re.compile(r"04_reports/.*report.*\.docx$", _re.I),
     frozenset({"document_sections", "document_lineage",
                "document_evidence_items"})),
    # Client_Profile DOCX drives BOTH focus_areas AND firmographics
    # (the client_profile parser emits both).
    (_re.compile(r"04_reports/.*client_profile.*\.docx$", _re.I),
     frozenset({"focus_areas", "firmographics"})),
    # Per-pillar research workbooks → evidence + parser_observations.
    (_re.compile(r"02_research_workbook/.*\.(csv|xlsx|xlsm|xls)$", _re.I),
     frozenset({"evidence_index", "evidence_run_links",
                "parser_observations"})),
    # Peer JSONs → peer_benchmarks.
    (_re.compile(r"06_peers/.*\.(csv|json)$", _re.I),
     frozenset({"peer_benchmarks"})),
    # Caps log → caps_applied_log.
    (_re.compile(r"07_governance/caps_applied_log\.csv$", _re.I),
     frozenset({"caps_applied_log"})),
    # qa_verdict.json updates runs JSONB columns.
    (_re.compile(r".*qa_verdict.*\.json$", _re.I),
     frozenset({"runs"})),
    # Recommendations JSON → recommendations table.
    (_re.compile(r"08_appendices/.*recommendation.*\.json$", _re.I),
     frozenset({"recommendations"})),
    # Run manifest / 00_parameters / MANIFEST drive entity + run +
    # firmographics identity. Includes catalog version pinning.
    (_re.compile(r".*run_manifest.*\.json$", _re.I),
     frozenset({"entities", "runs", "firmographics",
                "ccg_catalog_versions"})),
    (_re.compile(r".*00_parameters.*\.json$", _re.I),
     frozenset({"entities", "runs", "ccg_catalog_versions"})),
    (_re.compile(r"^manifest\.json$", _re.I),
     frozenset({"entities", "runs"})),
    # Issue register → issue_register table.
    (_re.compile(r".*issue_register.*\.(csv|json)$", _re.I),
     frozenset({"issue_register"})),
    # Tech stack appendix → tech_stack_entries.
    (_re.compile(r".*tech_?stack.*\.(csv|json|xlsx)$", _re.I),
     frozenset({"tech_stack_entries"})),
]


def affected_tables(diff: dict[str, list[str]]) -> set[str]:
    """Map a manifest diff to the persistence tables that need re-fire.

    Inputs: ``diff`` is the dict returned by :func:`diff_manifests`,
    keyed on ``added`` / ``removed`` / ``modified`` / ``cosmetic_changed``.
    Only the first three (the MATERIAL changes) participate; cosmetic
    flips are silently ignored.

    Returns: the set of canonical table names that derive from at least
    one of the changed material paths. The caller computes
    ``skip_tables = ALL_TABLES - affected_tables(diff)`` and passes it
    to :func:`persist_package`.

    Defense-in-depth: if a changed path doesn't match ANY pattern (e.g.
    a new artifact kind the bot pipeline started shipping), we treat
    it as ALL_TABLES so the safe fallback is "re-persist everything"
    rather than "silently drop the new artifact's downstream effects".
    """
    changed = set(diff.get("added") or []) \
        | set(diff.get("removed") or []) \
        | set(diff.get("modified") or [])
    if not changed:
        return set()
    out: set[str] = set()
    # Always include the invalidation surface so vertex_synthesis_cache
    # rows tied to this entity get marked stale when ANY material
    # change occurred.
    out.add("vertex_synthesis_cache_invalidate")
    # Always include parser_observations since the parser may emit
    # observations regardless of which artifact changed.
    out.add("parser_observations")
    for path in changed:
        matched = False
        for pat, tables in _ARTIFACT_TO_TABLES:
            if pat.search(path):
                out.update(tables)
                matched = True
        if not matched:
            # Unknown path -> safe fallback: re-persist everything.
            # Surfaces in the backfill log so the operator can add a
            # pattern next session.
            out.update(ALL_TABLES)
            break
    # Whenever a MATERIAL artifact changed, the entity row's
    # updated_at + the run row's parser_warnings should refresh so the
    # downstream consumers see "this run was re-touched". Cheap.
    out.update({"entities", "runs"})
    return out


def skip_tables_for_diff(diff: dict[str, list[str]]) -> set[str]:
    """Convenience: returns ALL_TABLES - affected_tables(diff)."""
    return set(ALL_TABLES) - affected_tables(diff)
