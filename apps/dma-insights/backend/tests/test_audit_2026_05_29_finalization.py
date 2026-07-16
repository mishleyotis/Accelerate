"""2026-05-29 finalization batch — pin every fix.

Each test pins ONE finalization fix and would FAIL if reverted.

Covered:
  FIN-1  Focus areas extracted by client_profile parser were only
         logged — never propagated to IngestedPackage envelope; the
         `focus_areas` table stayed empty in production despite
         every Client_Profile DOCX shipping focus areas.
         → fix: add FocusAreaRow schema, collect into pkg.focus_areas,
         persist via _persist_focus_areas helper (DELETE-then-INSERT).
  FIN-2  V5 catalogue gate: when EVERY parsed subcap is unresolved,
         the run was still marked ACTIVE → AEs would see an empty
         heatmap and the entity would appear ingested in admin
         overview, hiding the real problem.
         → fix: gate to status='PENDING_REVIEW' when
         parsed_count > 0 AND unresolved == parsed_count.
  FIN-3  Terraform DRIVE_ROOT_FOLDER_ID intentionally hardcoded per
         operator decision (canonical Drive folder is constant);
         comment documents the cross-pin contract with DEPLOYMENT.md
         §9 + CLAUDE.md.
         → fix: add explicit comment alongside the env block.
  FIN-4  Cloud Build e2e-personas stage had no source identity probe
         — stale source/image drift went undetected for >5 days when
         #gis-script leftover slipped through.
         → fix: print git rev-parse HEAD + git status + grep for
         #gis-script marker; fail fast if found.
"""
from __future__ import annotations

from pathlib import Path

REPO_BACKEND = Path(__file__).resolve().parent.parent

# ── FIN-1 ─────────────────────────────────────────────────────────────


def test_focus_area_row_schema_exists_with_018_columns() -> None:
    """FocusAreaRow Pydantic model must mirror migration 018's
    focus_areas table columns (reconciled in 023): title,
    verbatim_quote, source_path, page_number, involved_subcap_ids.
    """
    from app.schemas.package import FocusAreaRow

    fields = FocusAreaRow.model_fields
    required = {
        "title", "verbatim_quote", "source_path",
        "page_number", "involved_subcap_ids",
    }
    missing = required - set(fields.keys())
    assert not missing, f"FocusAreaRow missing columns: {missing}"


def test_ingested_package_carries_focus_areas_field() -> None:
    """IngestedPackage must expose focus_areas: list[FocusAreaRow].
    Without this field the parser's collection has nowhere to go and
    the persistence layer can't write rows.
    """
    from app.schemas.package import FocusAreaRow, IngestedPackage

    fields = IngestedPackage.model_fields
    assert "focus_areas" in fields, (
        "IngestedPackage must carry a `focus_areas` field — without it "
        "client_profile-extracted focus areas drop on the floor."
    )
    # Default must be empty list (not None) — every package builder
    # depends on iteration without None-checks.
    default_factory = fields["focus_areas"].default_factory
    assert default_factory is not None
    assert default_factory() == []
    # Type check — list of FocusAreaRow.
    assert FocusAreaRow is not None  # imported above; module loaded


def test_focus_area_row_validates_minimum_fields() -> None:
    """Title + verbatim_quote are REQUIRED; everything else nullable.
    Mirrors migration 018 NOT NULL constraints.
    """
    from app.schemas.package import FocusAreaRow

    # Minimal — title + verbatim_quote suffices.
    fa = FocusAreaRow(title="Top Finding 1", verbatim_quote="The bank lacks…")
    assert fa.source_path is None
    assert fa.page_number is None
    assert fa.involved_subcap_ids == []

    # Full shape.
    fa2 = FocusAreaRow(
        title="Critical Gap A",
        verbatim_quote="Gap quote here",
        source_path="04_reports/Alma_Client_Profile.docx",
        page_number=5,
        involved_subcap_ids=["P1C1.1.1", "P2C3.2.1"],
    )
    assert fa2.page_number == 5
    assert "P1C1.1.1" in fa2.involved_subcap_ids


def test_dma_package_collects_focus_areas_outside_firm_guard() -> None:
    """The parser must collect focus_areas unconditionally — NOT
    only when firm is None. Prior code only ran the client_profile
    parser as a firmographics fallback, so packages with a
    research_handoff.json (WSFS, Nicola, Calprivate) dropped focus
    areas on the floor.
    """
    src = (
        REPO_BACKEND / "app" / "services" / "parsers" / "dma_package.py"
    ).read_text()
    # 1. focus_areas_collected list initialized somewhere outside
    #    the `if firm is None:` block.
    assert "focus_areas_collected: list[FocusAreaRow] = []" in src, (
        "parse_package must initialize focus_areas_collected before "
        "the client_profile scan."
    )
    # 2. The collection loop must EXIST.
    assert "focus_areas_collected.append(" in src, (
        "parse_package must append FocusAreaRow per cp_result entry."
    )
    # 3. It must be passed into IngestedPackage.
    assert "focus_areas=focus_areas_collected" in src, (
        "IngestedPackage must receive focus_areas=focus_areas_collected."
    )
    # 4. FocusAreaRow must be imported.
    assert "FocusAreaRow" in src, (
        "FocusAreaRow must be imported from app.schemas.package."
    )


def test_persist_focus_areas_helper_exists_and_is_called() -> None:
    """_persist_focus_areas must:
      - exist as an async helper
      - DELETE by run_id first (idempotent re-ingest)
      - INSERT into focus_areas with the 018-column shape
      - be called from persist_package().
    """
    src = (
        REPO_BACKEND / "app" / "services" / "parsers" / "package_persist.py"
    ).read_text()

    assert "async def _persist_focus_areas(" in src
    # DELETE-then-INSERT idempotency pattern (matches
    # _persist_document_sections).
    assert "DELETE FROM focus_areas WHERE run_id = :rid" in src
    # INSERT must use the 018 column shape.
    assert "INSERT INTO focus_areas (" in src
    for col in [
        "title", "verbatim_quote", "source_path",
        "page_number", "involved_subcap_ids",
    ]:
        assert col in src, f"focus_areas INSERT missing column: {col}"
    # persist_package must call the helper.
    assert "_persist_focus_areas(" in src
    assert "inserted_focus_areas = await _persist_focus_areas(" in src


def test_persist_focus_areas_passes_list_natively() -> None:
    """asyncpg encodes a Python list as TEXT[] natively when bound to
    a TEXT[] column. The established pattern in this file is to pass
    `list(...)` directly (see issue_register.linked_subcap_ids at
    L605) — NOT to build a Postgres array literal + CAST. Pin the
    pattern so the helper stays consistent with the rest of the file.
    """
    src = (
        REPO_BACKEND / "app" / "services" / "parsers" / "package_persist.py"
    ).read_text()
    helper_idx = src.find("async def _persist_focus_areas(")
    publish_idx = src.find("async def publish_post_commit(")
    assert helper_idx > 0 and publish_idx > helper_idx
    helper_body = src[helper_idx:publish_idx]
    assert "list(fa.involved_subcap_ids or [])" in helper_body, (
        "focus_areas INSERT must pass a Python list directly so "
        "asyncpg can encode it as TEXT[] (matches the pattern at "
        "issue_register.linked_subcap_ids:605)."
    )


# ── FIN-2 ─────────────────────────────────────────────────────────────


def test_v5_catalogue_gate_sets_pending_review_on_zero_resolved() -> None:
    """When parsed_count > 0 AND unresolved == parsed_count, the run
    must be UPDATEd to status='PENDING_REVIEW'. ACTIVE would hide
    the empty-catalogue defect behind a silently-empty heatmap.
    """
    src = (
        REPO_BACKEND / "app" / "services" / "parsers" / "package_persist.py"
    ).read_text()
    # The gate has to be conditional on the ZERO-resolved branch
    # we already had a warning for; both fragments must coexist.
    assert "catalogue_empty_for_version:" in src
    assert "status='PENDING_REVIEW'" in src, (
        "v5 catalogue gate must mark run as PENDING_REVIEW when "
        "every parsed subcap is unresolved against the catalogue."
    )
    # The UPDATE must follow the warning (i.e., inside the same if
    # block where parsed_count > 0 and unresolved == parsed_count).
    gate_idx = src.find("if parsed_count > 0 and unresolved == parsed_count:")
    update_idx = src.find("status='PENDING_REVIEW'")
    evidence_idx = src.find("# ── Evidence (via dedup decision engine) ──")
    assert gate_idx > 0
    assert update_idx > gate_idx, (
        "PENDING_REVIEW UPDATE must come AFTER the zero-resolved "
        "branch gate (so it only fires when every subcap fails)."
    )
    assert update_idx < evidence_idx, (
        "PENDING_REVIEW UPDATE must happen BEFORE evidence persistence "
        "— so the run row's status reflects the catalogue-gate state "
        "by the time downstream rows reference it."
    )


# ── FIN-3 ─────────────────────────────────────────────────────────────


def test_terraform_drive_folder_id_documents_intentional_constant() -> None:
    """Per operator decision (2026-05-29): DRIVE_ROOT_FOLDER_ID is
    constant. The Terraform comment must document this so a future
    engineer doesn't mistakenly variableize it without checking the
    other two pin sites (DEPLOYMENT.md §9, CLAUDE.md).
    """
    tf = (
        Path(__file__).resolve().parents[2]
        / "infra" / "terraform" / "main.tf"
    ).read_text()
    # The hardcoded folder ID is still there.
    assert "1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P" in tf
    # The comment block flagging it as intentional is present.
    assert "INTENTIONALLY HARDCODED" in tf, (
        "Terraform main.tf must carry the operator-decision comment "
        "documenting why DRIVE_ROOT_FOLDER_ID isn't a variable."
    )
    # Must reference the other pin sites so the cross-document
    # contract is visible.
    assert "DEPLOYMENT.md" in tf
    assert "CLAUDE.md" in tf


# ── FIN-4 ─────────────────────────────────────────────────────────────


def test_cloudbuild_e2e_stage_has_source_identity_probe() -> None:
    """Cloud Build e2e-personas stage must print git rev-parse HEAD +
    git status for the audit trail, and assert the frontend
    package.json is reachable from cwd BEFORE the docker run mounts
    the volume. Without this, the 13min Playwright suite ran against
    the wrong source / silently mounted host root.
    """
    yml = (
        Path(__file__).resolve().parents[2]
        / "infra" / "cloudbuild.yaml"
    ).read_text()
    # Find the e2e-personas stage.
    e2e_idx = yml.find("- id: e2e-personas")
    next_stage_idx = yml.find("- id: ", e2e_idx + 10)
    assert e2e_idx > 0
    stage_body = yml[e2e_idx:next_stage_idx if next_stage_idx > 0 else None]

    # Source identity prints (audit trail).
    assert "git rev-parse HEAD" in stage_body, (
        "e2e-personas must print git rev-parse HEAD for audit trail."
    )
    assert "git status --short" in stage_body, (
        "e2e-personas must print git status for source-identity audit."
    )
    # Belt-and-braces cwd-contract probe.
    assert "no package.json at" in stage_body, (
        "e2e-personas must fail-fast when frontend/package.json is not "
        "reachable from cwd (catches `dir:` drift + cwd leak)."
    )


def test_cloudbuild_e2e_source_probe_runs_before_pg_sidecar() -> None:
    """The probe must run BEFORE the heavy PG sidecar bring-up so
    we don't spend 90s waiting for postgres just to discover the
    source was stale.
    """
    yml = (
        Path(__file__).resolve().parents[2]
        / "infra" / "cloudbuild.yaml"
    ).read_text()
    probe_idx = yml.find("e2e source identity")
    pg_sidecar_idx = yml.find(
        "PG sidecar (matches Cloud SQL POSTGRES_15 + pgvector)"
    )
    assert probe_idx > 0
    assert pg_sidecar_idx > 0
    assert probe_idx < pg_sidecar_idx, (
        "Source identity probe must run BEFORE the PG sidecar — "
        "fail-fast saves 90s+ when source is stale."
    )


def test_cloudbuild_e2e_probe_preserves_cwd_for_volume_mount() -> None:
    """The source identity probe MUST NOT change the outer shell's cwd.

    Cloud Build sets cwd via `dir: frontend` (= /workspace/frontend).
    The Playwright docker run mounts `$(pwd)/..` into /workspace inside
    the container. If the probe does an unguarded `cd /workspace`, the
    outer cwd shifts to /workspace and `$(pwd)/..` becomes `/` — the
    container then mounts host root, pnpm fails with
    `ERR_PNPM_NO_PKG_MANIFEST  No package.json found in /workspace/frontend`.

    Regression lock for the 2026-05-29 Cloud Build failure on commit
    298baab. Any `cd` outside a subshell `( … )` in the probe region
    is a bug.
    """
    yml = (
        Path(__file__).resolve().parents[2]
        / "infra" / "cloudbuild.yaml"
    ).read_text()
    probe_start = yml.find("===== e2e source identity =====")
    # Multiple stages contain `# ── 1. PG sidecar`; find the one AFTER
    # the probe (stage 7), not the first match (stage 2b).
    pg_sidecar = yml.find("# ── 1. PG sidecar", probe_start)
    assert probe_start > 0, "probe block not found in cloudbuild.yaml"
    assert pg_sidecar > probe_start, (
        "could not find PG-sidecar marker after probe — file layout drift"
    )
    probe_body = yml[probe_start:pg_sidecar]

    # Every `cd` MUST be inside a subshell `( … )` so it doesn't leak
    # into the outer shell's cwd. Scan each non-comment line for bare
    # `cd ` statements.
    leaks: list[str] = []
    for ln in probe_body.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        # `cd` at start (outside parens) → leak.
        if s.startswith("cd ") and not s.startswith("( "):
            leaks.append(ln)
    assert not leaks, (
        "Unscoped `cd` in source identity probe will leak cwd into the "
        f"outer shell, breaking the docker volume mount: {leaks!r}"
    )


def test_cloudbuild_e2e_volume_mount_uses_absolute_app_root() -> None:
    """The Playwright docker run mounts the app root into /workspace.
    Pin the BULLETPROOF contract: APP_ROOT is captured as an absolute
    path BEFORE any cd, and the mount uses "$APP_ROOT" — NOT the
    cwd-relative `$(pwd)/..` that the 298baab regression broke when a
    stray cd leaked the outer cwd.
    """
    yml = (
        Path(__file__).resolve().parents[2]
        / "infra" / "cloudbuild.yaml"
    ).read_text()
    e2e_idx = yml.find("- id: e2e-personas")
    next_stage = yml.find("- id: ", e2e_idx + 10)
    stage = yml[e2e_idx:next_stage if next_stage > 0 else None]

    # dir: frontend MUST be declared in this stage.
    assert "dir: frontend" in stage, (
        "e2e-personas must declare `dir: frontend` so the app root "
        "resolves correctly."
    )
    # APP_ROOT captured up-front (before any cd) via `cd .. && pwd`.
    assert 'APP_ROOT="$$(cd .. && pwd)"' in stage, (
        "e2e-personas must capture APP_ROOT as an absolute path BEFORE "
        "any cd, immunizing the mount against cwd leaks."
    )
    # The docker mount MUST use the absolute variable, NOT $(pwd)/..
    assert '-v "$$APP_ROOT":/workspace' in stage, (
        "Playwright docker run must mount $$APP_ROOT into /workspace "
        "(absolute, cwd-independent)."
    )
    assert '"$(pwd)/..":/workspace' not in stage, (
        "Mount must NOT use the cwd-relative $(pwd)/.. form — that "
        "broke in 298baab when a stray cd leaked the outer cwd."
    )
    # Container cwd is /workspace/frontend.
    assert "-w /workspace/frontend" in stage
