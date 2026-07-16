"""2026-05-29 second-pass audit P0/P1 regressions — pin every fix.

Each test pins ONE fix and would FAIL if the fix were reverted.

Covered:
  AUD-1  RunSummary.data_source schema drift: rejected DRIVE_BACKFILL +
         BOT_REQUEST that migration 021 + production writers actually use.
         → fix: schemas/entities.py Literal mirrors migration 021.
  AUD-2  cloud_run_dispatch embedder default args = ["--once"], but
         workers/embedder/main.py argparse rejected --once → admin
         "Embeddings" button always exited with argparse error.
         → fix: add --once to embedder argparse; --once → --since 24h-ago.
  AUD-3  cloud_run_dispatch ccg_loader default args = [], but
         workers/ccg_loader/main.py REQUIRES --version + --workbooks-dir
         → admin "CCG Loader" button always exited with
         "the following arguments are required".
         → fix: dispatch defaults mirror Terraform's Cloud Run Job spec.
  AUD-4  ingest_package pre-extract warnings (deck-skipped + duplicate
         zip entry) returned in HTTP response but NOT persisted to
         runs.parser_warnings → Admin Import Audit + D1 chip dropped
         the warnings.
         → fix: merge pre_extract_warnings into pkg.parser_warnings
         BEFORE persist_package() so they land on the run row.
  AUD-5  RAG router validated FABRICATED citations only. A plausible
         Gemini answer with ZERO citations passed validator-clean,
         even with require_citations=True AND a non-empty bundle.
         → fix: when require_citations AND bundle.items AND no
         citations → fail closed, fallback_used=True, alert row.
  AUD-6  package_persist used display_id-only ON CONFLICT — same
         Drive folder + new request_id = duplicate entity row,
         fragmenting customer history across two entities.
         → fix: SELECT … FOR UPDATE by drive_folder_id BEFORE
         display_id upsert; reuse entity_id when matched.
"""
from __future__ import annotations

from datetime import UTC
from typing import get_args

# ── AUD-1 ─────────────────────────────────────────────────────────────


def test_run_summary_accepts_every_migration_021_value() -> None:
    """RunSummary.data_source must accept every value in
    alembic/versions/021_runs_drive_backfill.py's CHECK constraint —
    DRIVE_PARSE, DRIVE_BACKFILL, PROJECT_API, MANUAL_BACKFILL,
    BOT_REQUEST. Prior schema rejected DRIVE_BACKFILL (which
    historical_backfill.py writes on every run) AND BOT_REQUEST
    (which the n8n bot loop writes).
    """
    from app.schemas.entities import RunSummary

    # Inspect the Literal annotation directly.
    fields = RunSummary.model_fields
    annotation = fields["data_source"].annotation
    allowed = set(get_args(annotation))
    required = {
        "DRIVE_PARSE", "DRIVE_BACKFILL", "PROJECT_API",
        "MANUAL_BACKFILL", "BOT_REQUEST",
    }
    missing = required - allowed
    assert not missing, f"RunSummary.data_source missing values: {missing}"


def test_run_summary_serializes_drive_backfill_run() -> None:
    """A fully-populated DRIVE_BACKFILL run instance must validate
    cleanly through Pydantic — this is what dashboard/overview/runs
    endpoints construct.
    """
    from datetime import datetime

    from app.schemas.entities import RunSummary

    now = datetime.now(UTC)
    rs = RunSummary(
        id="00000000-0000-0000-0000-000000000001",
        request_id="DMA-ASM-WSFS-20260519-0001",
        status="ACTIVE",
        data_source="DRIVE_BACKFILL",
        evidence_mode="public",
        ccg_catalog_version="v5.0",
        created_at=now,
        updated_at=now,
    )
    assert rs.data_source == "DRIVE_BACKFILL"


def test_run_summary_serializes_bot_request_run() -> None:
    """Bot-originated runs (data_source=BOT_REQUEST) must also
    serialize cleanly.
    """
    from datetime import datetime

    from app.schemas.entities import RunSummary

    now = datetime.now(UTC)
    rs = RunSummary(
        id="00000000-0000-0000-0000-000000000002",
        request_id="REQ-DEADBEEF",
        status="ACTIVE",
        data_source="BOT_REQUEST",
        evidence_mode="hybrid",
        ccg_catalog_version="v7.0",
        created_at=now,
        updated_at=now,
    )
    assert rs.data_source == "BOT_REQUEST"


# ── AUD-2 ─────────────────────────────────────────────────────────────


def test_embedder_main_argparse_accepts_once() -> None:
    """Admin's `JOB_DISPATCH["embedder"]` sends ["--once"]; the worker's
    argparse must accept it without exiting with
    'unrecognized arguments: --once'. We assert on the source file
    rather than importing workers.embedder because the workers/ tree
    isn't on the backend test PYTHONPATH.
    """
    from pathlib import Path

    src_path = (
        Path(__file__).resolve().parent.parent.parent
        / "workers" / "embedder" / "main.py"
    )
    text = src_path.read_text()
    assert 'parser.add_argument("--once"' in text, (
        "workers/embedder/main.py argparse must declare --once via "
        'parser.add_argument("--once", …) — '
        "JOB_DISPATCH['embedder'] sends it as a default arg."
    )


def test_embedder_once_maps_to_24h_since_window() -> None:
    """`--once` is documented as 'process every run from the last 24h
    that lacks section_embeddings rows'. The argparse handler converts
    --once to --since (24h-ago iso) when no other selector is set, so
    downstream `_main_body` doesn't need a special case.
    """
    src_path = (
        __import__("pathlib").Path(__file__).resolve().parent.parent.parent
        / "workers" / "embedder" / "main.py"
    )
    text = src_path.read_text()
    # The merge logic must reference both --once and --since in
    # close proximity so a future refactor that splits them apart
    # has to consciously address the documented behavior.
    assert "args.once" in text and "args.since" in text and "timedelta(days=1)" in text, (
        "embedder must convert --once into a --since 24h-ago window "
        "(2026-05-29 audit contract)"
    )


# ── AUD-3 ─────────────────────────────────────────────────────────────


def test_ccg_loader_dispatch_default_args_satisfy_argparse() -> None:
    """cloud_run_dispatch.JOB_DISPATCH['ccg_loader'] must supply both
    --version AND --workbooks-dir, otherwise the worker's argparse
    fails with 'the following arguments are required'.
    """
    from app.services.cloud_run_dispatch import JOB_DISPATCH

    _cr_name, default_args, _py_module = JOB_DISPATCH["ccg_loader"]
    assert "--version" in default_args
    assert "--workbooks-dir" in default_args
    # And the values must be non-empty strings, not the next flag.
    version_idx = default_args.index("--version")
    assert version_idx + 1 < len(default_args)
    version_val = default_args[version_idx + 1]
    assert version_val and not version_val.startswith("--")
    workbooks_idx = default_args.index("--workbooks-dir")
    assert workbooks_idx + 1 < len(default_args)
    workbooks_val = default_args[workbooks_idx + 1]
    assert workbooks_val and not workbooks_val.startswith("--")


def test_every_dispatch_default_arg_is_accepted_by_worker_argparse() -> None:
    """Cross-check: every (job_name, default_args) pair in
    JOB_DISPATCH must reference flags that the corresponding worker's
    argparse actually declares. Catches the next embedder/ccg_loader
    -style drift before admin deploys it.
    """
    from pathlib import Path

    from app.services.cloud_run_dispatch import JOB_DISPATCH

    workers_root = Path(__file__).resolve().parent.parent.parent / "workers"
    backend_scripts = Path(__file__).resolve().parent.parent / "app" / "scripts"

    missing: dict[str, list[str]] = {}
    for job_name, (_cr_name, default_args, py_module) in JOB_DISPATCH.items():
        # Resolve the module file.
        rel = py_module.replace(".", "/") + ".py"
        if py_module.startswith("workers."):
            src_path = workers_root.parent / rel
        elif py_module.startswith("app.scripts."):
            src_path = backend_scripts.parent.parent / rel
        else:
            continue
        if not src_path.exists():
            continue
        src = src_path.read_text()
        for arg in default_args:
            # Confirm the flag name is referenced in add_argument(...);
            # we don't reproduce argparse here.
            if (
                arg.startswith("--")
                and f'"{arg}"' not in src
                and f"'{arg}'" not in src
            ):
                missing.setdefault(job_name, []).append(arg)

    assert not missing, (
        f"JOB_DISPATCH default args reference flags not declared in worker "
        f"argparse: {missing}. Admin button presses for these jobs would "
        f"exit with 'argparse: unrecognized arguments' or required-arg errors."
    )


# ── AUD-4 ─────────────────────────────────────────────────────────────


def test_ingest_package_pre_extract_warnings_persist_to_run() -> None:
    """The ingest_package route's pre-extract warnings
    (skipped_non_ingested_artifact + duplicate_zip_entry) must merge
    into pkg.parser_warnings BEFORE persist_package() so they land on
    `runs.parser_warnings`. Prior code only added them to the HTTP
    response payload — the Admin Import Audit + D1 chip dropped them.
    """
    src_path = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "app" / "routers" / "ingest_package.py"
    )
    text = src_path.read_text()
    # Find the line that merges pre_extract_warnings into pkg.parser_warnings.
    merge_into_pkg = (
        "pkg.parser_warnings = list(pkg.parser_warnings) + pre_extract_warnings"
    )
    assert merge_into_pkg in text, (
        "ingest_package must merge pre_extract_warnings into "
        "pkg.parser_warnings BEFORE persist_package() — otherwise "
        "skipped-deck + duplicate-zip-entry warnings drop on the floor."
    )
    # Locate the persist_package call and confirm the merge runs first.
    merge_idx = text.find(merge_into_pkg)
    persist_idx = text.find("run_id, warnings = await persist_package(session, pkg)")
    assert 0 < merge_idx < persist_idx, (
        "Merge into pkg.parser_warnings must happen BEFORE persist_package() — "
        "the run row is written by persist_package and that's the row that "
        "ends up on runs.parser_warnings."
    )


# ── AUD-5 ─────────────────────────────────────────────────────────────


def test_rag_router_fails_closed_when_citations_required_but_missing() -> None:
    """When require_citations=True AND bundle has evidence AND the
    Gemini answer omits citations entirely, the router must fail
    closed (fallback_used=True, alert row inserted, no cache write).
    """
    src_path = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "app" / "routers" / "rag.py"
    )
    text = src_path.read_text()
    # The new branch must reference all three predicates from the
    # contract: require_citations, bundle.items, and the empty-
    # citation case. Allow for whitespace drift; check the
    # predicate fragments individually.
    for needle in [
        "body.require_citations",
        "and bundle.items",
        "not mentioned and not mentioned_sections",
        "citation_required_but_missing",
        '"missing_citations": True',
    ]:
        assert needle in text, (
            f"rag.py missing citation-required enforcement token: {needle!r}. "
            "Without it, a Gemini answer with zero citations passes "
            "validator-clean even when bundle has evidence — exactly the "
            "ungrounded-but-confident failure the audit pinned."
        )


# ── AUD-6 ─────────────────────────────────────────────────────────────


def test_package_persist_dedups_by_drive_folder_id_before_display_id() -> None:
    """package_persist must SELECT existing entities by drive_folder_id
    BEFORE the display_id-based INSERT/UPSERT. Otherwise the same
    Drive folder ingested twice with different request_ids creates
    two SEPARATE entity rows — fragmenting customer history.
    """
    src_path = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "app" / "services" / "parsers" / "package_persist.py"
    )
    text = src_path.read_text()
    # The pre-lookup is split across Python string-concat lines, so
    # search for the two fragments separately. 2026-06-10: the SELECT
    # also pulls `name` (the junk-name guard compares the incoming name
    # against the existing one) and the INSERT gained the
    # inferred_from_source/inferred_at review columns, wrapping the
    # column list across lines — match the stable prefix.
    pre_lookup_part_1 = "SELECT id, name FROM entities"
    pre_lookup_part_2 = "drive_folder_id = :dfid FOR UPDATE"
    insert = "INSERT INTO entities (name, display_id, subvertical, status,"
    pre_idx_1 = text.find(pre_lookup_part_1)
    pre_idx_2 = text.find(pre_lookup_part_2)
    insert_idx = text.find(insert)
    assert pre_idx_1 > 0 and pre_idx_2 > 0, (
        "package_persist must SELECT existing entity by drive_folder_id "
        "with FOR UPDATE before falling back to display_id upsert "
        "(2026-05-29 audit dedup contract)."
    )
    # Both fragments must precede the INSERT — and they must be adjacent
    # to each other (consecutive Python string-literal lines).
    assert pre_idx_2 - pre_idx_1 < 200, (
        "The SELECT lookup fragments must be adjacent — "
        "ensure they form a single SQL string."
    )
    assert pre_idx_1 < insert_idx, (
        "The drive_folder_id lookup must happen BEFORE the display_id "
        "upsert path — otherwise two backfills of the same Drive folder "
        "create two entities."
    )


def test_package_persist_reuses_entity_when_drive_folder_matches() -> None:
    """Documents the resulting contract: same drive_folder_id ⇒ same
    entity_id, even when display_id (which embeds run_id) differs.
    """
    src_path = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "app" / "services" / "parsers" / "package_persist.py"
    )
    text = src_path.read_text()
    # When the SELECT hits, we keep entity_id from the prior row AND
    # update metadata (name + subvertical). The display_id-based
    # INSERT path is skipped.
    # 2026-06-10: the metadata refresh became junk-name-guarded — a
    # junk incoming name never clobbers a clean existing one, so the
    # SET name is now a CASE on the :keep bind rather than a bare :name.
    for needle in [
        "if existing is not None:",
        "entity_id = existing.id",
        "name = CASE WHEN CAST(:keep AS BOOLEAN) THEN :name ELSE name END",
    ]:
        assert needle in text, (
            f"package_persist missing drive-folder dedup token: {needle!r}"
        )
