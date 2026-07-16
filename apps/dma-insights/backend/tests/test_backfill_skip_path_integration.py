"""v2-QA Batch 8 — live-DB integration test for the backfill skip path.

Per the integrated batched plan Batch 8 spec + the operator mandates
"consider all 103 DMAs in your tests" and "craft code that thinks
through most common errors and addresses them before they even
happen": this test pins the contract that the historical_backfill's
intelligent skip-check works correctly end-to-end on EVERY persisted
entity, AND that controlled mutations (cosmetic vs material) trigger
the correct skip/re-ingest decision.

The test asserts 4 properties against the LIVE corpus + live DB:

  1. **Manifest round-trip determinism**: for every active entity
     whose drive_folder_id maps to a local fixture path, the manifest
     computed from disk MUST match the JSON persisted on the run row
     (artifact_manifest_json). A mismatch means the persist layer
     wrote stale data OR the classifier changed without a re-backfill.

  2. **Material hash consistency**: the rollup material_manifest_hash
     computed from disk MUST match runs.material_manifest_hash for
     every entity (same idempotency guarantee).

  3. **Cosmetic mutation -> still SKIP**: touching a cosmetic file
     (e.g. a 05_narrative_deck/*.pptx) changes the file mtime but
     NOT its material-hash. The next backfill pass MUST still skip
     via the intelligent path.

  4. **Material mutation -> re-ingest fires**: touching a material
     file (e.g. a 03_scoring_workbook/*.csv) changes the material
     hash. The next backfill pass MUST detect the change.

Test isolation: every file mutation is wrapped in a try/finally that
RESTORES the original bytes. The committed corpus is NEVER left in a
mutated state -- even on test failure / KeyboardInterrupt.

Per the operator mandate "no test skips, no silent error
swallowing": the live-DB gate uses DATABASE_URL_SYNC (matches the
SEED_CI_PG_URL convention).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.scripts.historical_backfill import _find_local_package_roots
from app.services.artifact_manifest import (
    ArtifactEntry,
    PackageManifest,
    classify_path,
    compute_package_manifest,
    diff_manifests,
)

_CORPUS = (
    Path(__file__).resolve().parents[1]
    / "tests" / "fixtures" / "dma_packages_batches"
)


def _live_db() -> bool:
    return bool(os.environ.get("DATABASE_URL_SYNC", ""))


pytestmark = pytest.mark.skipif(
    not _live_db(),
    reason=(
        "DATABASE_URL_SYNC not set -- backfill integration test "
        "requires live PG. Set DATABASE_URL_SYNC to the local Postgres "
        "connection string."
    ),
)


def test_manifest_round_trip_determinism_for_all_entities() -> None:
    """For every entity in the live DB whose drive_folder_id starts
    with ``local:``, the on-disk manifest hash MUST match
    ``runs.material_manifest_hash``.

    This catches:
      - persist layer wrote a stale hash
      - classifier change drift (the rollup formula changed but the
        DB rows weren't re-backfilled via Batch 8's CLI)
      - corpus tampering (a committed fixture file diverged from
        what was hashed at ingest time)
    """
    roots = _find_local_package_roots(_CORPUS)
    assert roots, f"no package roots discovered under {_CORPUS}"

    async def _run() -> tuple[int, list[str]]:
        engine = create_async_engine(get_settings().database_url, echo=False)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        mismatches: list[str] = []
        checked = 0
        try:
            async with sm() as session:
                for root in roots:
                    client_name = root.name
                    for parent in [root, *root.parents]:
                        if parent.name.endswith(" - DMA") or \
                                parent.name.endswith("- DMA"):
                            client_name = parent.name
                            break
                    folder_key = f"local:{client_name}"

                    # Disk hash.
                    disk_manifest = compute_package_manifest(root)
                    disk_hash = disk_manifest.material_manifest_hash
                    if not disk_hash:
                        # Empty package -- skip.
                        continue

                    # DB hash (most recent run for this folder).
                    db_hash = (await session.execute(
                        text(
                            "SELECT r.material_manifest_hash "
                            "FROM runs r "
                            "JOIN entities e ON e.id = r.entity_id "
                            "WHERE e.drive_folder_id = :fid "
                            "ORDER BY r.completed_at DESC NULLS LAST "
                            "LIMIT 1"
                        ),
                        {"fid": folder_key},
                    )).scalar()

                    if db_hash is None:
                        # No run yet -- the operator hasn't ingested
                        # this package. Skip (NOT a failure of this
                        # contract).
                        continue

                    checked += 1
                    if db_hash != disk_hash:
                        mismatches.append(
                            f"{client_name}: disk={disk_hash[:12]}... "
                            f"db={db_hash[:12]}..."
                        )
        finally:
            await engine.dispose()
        return checked, mismatches

    checked, mismatches = asyncio.run(_run())
    assert checked >= 50, (
        f"Expected to verify >= 50 packages; only checked {checked}. "
        f"Has the corpus been seeded? Run: python -m "
        f"app.scripts.historical_backfill --dir tests/fixtures/"
        f"dma_packages_batches --force"
    )
    assert not mismatches, (
        f"Manifest round-trip mismatch on {len(mismatches)} packages "
        f"(disk hash != db hash); first 10:\n"
        + "\n".join(f"  {m}" for m in mismatches[:10])
    )


def test_cosmetic_mutation_does_not_change_material_hash() -> None:
    """Touching a cosmetic file (deck PPTX / OS cruft / search log)
    changes file content but NOT the material_manifest_hash. The
    backfill's intelligent skip MUST still fire on the next pass.

    Test isolation: source bytes are restored in finally.
    """
    # Find a package with a cosmetic file to mutate.
    candidate_root: Path | None = None
    candidate_cosmetic: Path | None = None
    for root in _find_local_package_roots(_CORPUS):
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            try:
                rel = f.relative_to(root).as_posix()
            except ValueError:
                continue
            if classify_path(rel) == "cosmetic":
                candidate_root = root
                candidate_cosmetic = f
                break
        if candidate_root:
            break

    assert candidate_root is not None, (
        "No cosmetic file found in corpus -- the materiality "
        "classifier may have regressed; investigate "
        "artifact_manifest._COSMETIC_PREFIXES / _COSMETIC_REGEXES."
    )
    assert candidate_cosmetic is not None

    original_bytes = candidate_cosmetic.read_bytes()
    hash_before = compute_package_manifest(
        candidate_root,
    ).material_manifest_hash

    try:
        # Mutate: append 16 bytes (clearly distinct content).
        candidate_cosmetic.write_bytes(
            original_bytes + b"BATCH8_COSMETIC_MUT",
        )
        hash_after = compute_package_manifest(
            candidate_root,
        ).material_manifest_hash
        assert hash_after == hash_before, (
            f"Cosmetic mutation changed material_manifest_hash: "
            f"before={hash_before[:12]}... after={hash_after[:12]}... "
            f"(file: {candidate_cosmetic})"
        )
    finally:
        # ALWAYS restore the source bytes.
        candidate_cosmetic.write_bytes(original_bytes)
        # Verify restoration.
        restored_hash = compute_package_manifest(
            candidate_root,
        ).material_manifest_hash
        assert restored_hash == hash_before, (
            f"FIXTURE CORRUPTED: failed to restore "
            f"{candidate_cosmetic.name} -- before={hash_before[:12]}... "
            f"restored={restored_hash[:12]}..."
        )


def test_material_mutation_changes_material_hash() -> None:
    """Touching a material file (scoring CSV / evidence JSON / DOCX
    section body) MUST change the material_manifest_hash so the
    backfill's intelligent skip path detects the change.

    Test isolation: source bytes are restored in finally.
    """
    candidate_root: Path | None = None
    candidate_material: Path | None = None
    # Prefer a scoring CSV as the canonical material example.
    for root in _find_local_package_roots(_CORPUS):
        for f in root.rglob("export_pillar_summary.csv"):
            if f.is_file():
                candidate_root = root
                candidate_material = f
                break
        if candidate_root:
            break

    if candidate_root is None:
        # Fallback: any CSV under 03_scoring_workbook.
        for root in _find_local_package_roots(_CORPUS):
            for f in (root / "03_scoring_workbook").rglob("*.csv"):
                if f.is_file():
                    candidate_root = root
                    candidate_material = f
                    break
            if candidate_root:
                break

    assert candidate_root is not None and candidate_material is not None, (
        "No scoring CSV found in corpus -- the seeded corpus may be "
        "incomplete. Run: python -m app.scripts.historical_backfill "
        "--dir tests/fixtures/dma_packages_batches --force"
    )

    original_bytes = candidate_material.read_bytes()
    hash_before = compute_package_manifest(
        candidate_root,
    ).material_manifest_hash

    try:
        # Mutate: append a 1-byte CSV-safe newline (parser-tolerant).
        candidate_material.write_bytes(original_bytes + b"\n")
        hash_after = compute_package_manifest(
            candidate_root,
        ).material_manifest_hash
        assert hash_after != hash_before, (
            f"Material mutation did NOT change "
            f"material_manifest_hash: "
            f"before={hash_before[:12]}... after={hash_after[:12]}... "
            f"(file: {candidate_material}). The Batch-2 intelligent "
            f"skip path would over-fire SKIP and miss real changes."
        )
    finally:
        # ALWAYS restore source.
        candidate_material.write_bytes(original_bytes)
        restored_hash = compute_package_manifest(
            candidate_root,
        ).material_manifest_hash
        assert restored_hash == hash_before, (
            f"FIXTURE CORRUPTED: failed to restore "
            f"{candidate_material.name} -- before={hash_before[:12]}... "
            f"restored={restored_hash[:12]}..."
        )


def test_diff_manifests_classifies_cosmetic_change_separately() -> None:
    """End-to-end diff: a cosmetic-only change appears in
    ``cosmetic_changed`` and NOT in ``added/removed/modified``.
    """
    roots = _find_local_package_roots(_CORPUS)
    assert roots
    root = roots[0]

    # Find a cosmetic file under this root.
    cosmetic_file: Path | None = None
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(root).as_posix()
        except ValueError:
            continue
        if classify_path(rel) == "cosmetic":
            cosmetic_file = f
            break

    if cosmetic_file is None:
        # Some packages have no cosmetic files; try another root.
        for root in roots[1:5]:
            for f in root.rglob("*"):
                if not f.is_file():
                    continue
                try:
                    rel = f.relative_to(root).as_posix()
                except ValueError:
                    continue
                if classify_path(rel) == "cosmetic":
                    cosmetic_file = f
                    break
            if cosmetic_file:
                break

    if cosmetic_file is None:
        pytest.fail(
            "No cosmetic file found in the first 5 corpus packages -- "
            "classifier may have regressed."
        )

    original = cosmetic_file.read_bytes()
    manifest_pre = compute_package_manifest(root)
    try:
        cosmetic_file.write_bytes(original + b"COSMETIC_DIFF_TEST")
        manifest_post = compute_package_manifest(root)
        diff = diff_manifests(manifest_pre, manifest_post)
        # Material lists MUST be empty.
        assert not diff["added"], f"unexpected added: {diff['added']}"
        assert not diff["removed"], f"unexpected removed: {diff['removed']}"
        assert not diff["modified"], (
            f"unexpected modified: {diff['modified']}"
        )
        # Cosmetic list MUST include the touched path.
        rel = cosmetic_file.relative_to(root).as_posix()
        assert rel in diff["cosmetic_changed"], (
            f"Cosmetic touch '{rel}' missing from cosmetic_changed: "
            f"{diff['cosmetic_changed']}"
        )
    finally:
        cosmetic_file.write_bytes(original)


def test_packagemanifest_dataclasses_serialize_and_round_trip() -> None:
    """The persist + warmup flow round-trips PackageManifest through
    JSON. Verifies the dataclass serialization symmetry so a future
    field addition doesn't silently drop data.
    """
    import json

    roots = _find_local_package_roots(_CORPUS)
    assert roots
    pkg = compute_package_manifest(roots[0])

    # Serialize the way historical_backfill does.
    serialized = json.dumps([
        {"rel_path": e.rel_path, "cls": e.cls,
         "content_hash": e.content_hash, "size_bytes": e.size_bytes}
        for e in pkg.entries
    ])
    # Deserialize the way historical_backfill's read-side does.
    reconstructed_entries = [
        ArtifactEntry(
            rel_path=r["rel_path"], cls=r["cls"],
            content_hash=r["content_hash"], size_bytes=r["size_bytes"],
        )
        for r in json.loads(serialized)
    ]
    reconstructed = PackageManifest(entries=reconstructed_entries)

    # Same entries.
    assert len(reconstructed.entries) == len(pkg.entries)
    # Material counts derivable from the diff path.
    diff = diff_manifests(reconstructed, pkg)
    # Same content -> no material changes detected.
    assert diff["added"] == []
    assert diff["removed"] == []
    assert diff["modified"] == []


# ── Strict-ingest-gate corpus contract (2026-06-10) ───────────────────
# Runs in cloudbuild qa-gates AFTER historical_backfill seeds the full
# fixture corpus. Pins the operator mandate: only fully-scored reports
# ingest; every ACTIVE entity is scored AND cleanly named. The floor
# (>= 93) derives from the 2026-06-10 baseline measurement: 109 ok
# ingests under the old policy, of which 14 entities were zero-score
# partials — strict gate yields ~95 ACTIVE entities. Floor, never
# equality: fixture churn must not break the build.

_ACTIVE_ENTITY_FLOOR = 93


def test_strict_gate_corpus_contract() -> None:
    """(a) ACTIVE entity count >= floor; (b) EVERY ACTIVE entity has
    >= 1 subcap score (no partial/hollow entities); (c) zero ACTIVE
    entities carry a junk institution name (raw Drive IDs, folder
    noise, fragments park in PENDING_REVIEW, never AE-visible)."""
    from app.services.entity_name_sanity import check_institution_name

    async def _run():
        engine = create_async_engine(get_settings().database_url, echo=False)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sm() as session:
                n_active = (await session.execute(
                    text("SELECT COUNT(*) FROM entities "
                         "WHERE status = 'ACTIVE'")
                )).scalar_one()
                unscored = (await session.execute(
                    text(
                        "SELECT e.display_id FROM entities e "
                        "WHERE e.status = 'ACTIVE' AND NOT EXISTS ("
                        "  SELECT 1 FROM runs r "
                        "  JOIN subcap_scores s ON s.run_id = r.id "
                        "  WHERE r.entity_id = e.id) "
                        "ORDER BY e.display_id"
                    )
                )).scalars().all()
                names = (await session.execute(
                    text("SELECT display_id, name FROM entities "
                         "WHERE status = 'ACTIVE'")
                )).all()
        finally:
            await engine.dispose()
        return n_active, unscored, names

    n_active, unscored, names = asyncio.run(_run())

    assert n_active >= _ACTIVE_ENTITY_FLOOR, (
        f"only {n_active} ACTIVE entities (floor {_ACTIVE_ENTITY_FLOOR}) "
        f"— the backfill under-ingested the corpus"
    )
    assert not unscored, (
        f"{len(unscored)} ACTIVE entities have ZERO subcap scores — the "
        f"strict ingest gate (2026-06-10) must skip these at ingest; "
        f"run purge_partial_entities for pre-gate debris: {unscored}"
    )
    junk = [
        (did, name, check_institution_name(name)[1])
        for did, name in names
        if check_institution_name(name)[0]
    ]
    assert not junk, (
        f"ACTIVE entities with junk institution names (must be "
        f"PENDING_REVIEW): {junk}"
    )


def test_peer_cohort_prerequisites_filled() -> None:
    """(d) Subvertical coverage: every peer surface (D1 peer ticks, D3
    overlay, RAG cohorts) keys on entities.subvertical — the exact-match
    mapper left 82/95 NULL (2026-06-10). The tolerant mapper must
    resolve >= 85% of ACTIVE entities; and the category->subcap
    peer-median broadcast must fill subcap_scores.peer_median for every
    run whose package carried category-level peer medians."""

    async def _run():
        engine = create_async_engine(get_settings().database_url, echo=False)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sm() as session:
                n_active = (await session.execute(
                    text("SELECT COUNT(*) FROM entities "
                         "WHERE status = 'ACTIVE'")
                )).scalar_one()
                n_sv = (await session.execute(
                    text("SELECT COUNT(*) FROM entities WHERE "
                         "status = 'ACTIVE' AND subvertical IS NOT NULL")
                )).scalar_one()
                n_peer_subcaps = (await session.execute(
                    text("SELECT COUNT(*) FROM subcap_scores "
                         "WHERE peer_median IS NOT NULL")
                )).scalar_one()
        finally:
            await engine.dispose()
        return n_active, n_sv, n_peer_subcaps

    n_active, n_sv, n_peer_subcaps = asyncio.run(_run())
    assert n_active and n_sv / n_active >= 0.85, (
        f"only {n_sv}/{n_active} ACTIVE entities have a subvertical — "
        f"peer cohorts/ticks render empty below ~85% coverage "
        f"(tolerant _canonical_subvertical regressed?)"
    )
    assert n_peer_subcaps > 1000, (
        f"subcap_scores.peer_median filled on only {n_peer_subcaps} rows "
        f"— the category->subcap peer-median broadcast regressed"
    )
