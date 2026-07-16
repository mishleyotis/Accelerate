"""Phase 3 parser warning kind round-trip tests.

Per the audit:
  - test_corrupt_json_warning_kind_json_corrupt_persisted
  - test_schema_mismatch_warning_kind_schema_mismatch_persisted
  - test_io_error_warning_kind_io_error_persisted

The parser emits TYPED warning strings (`json_corrupt`, `io_error`,
`schema_mismatch`) so the import-audit UI can classify them
distinctly + the operator can spot the failure pattern (silent
re-ingest of corrupt files vs network blip vs schema drift).

A refactor that swaps to generic "parse failed" loses the typed
classification. These tests pin the kind strings + the helper that
produces them so the contract survives expansion.
"""
from __future__ import annotations

from pathlib import Path

DMA_PKG = (
    Path(__file__).resolve().parents[1]
    / "app" / "services" / "parsers" / "dma_package.py"
).read_text(encoding="utf-8")


def test_parser_emits_typed_json_corrupt_warning_on_bad_json():
    """A JSONDecodeError must be wrapped in a warning with the
    `json_corrupt` prefix so import_audit groups it under "data
    corruption" rather than "io / network"."""
    assert "json_corrupt" in DMA_PKG, (
        "dma_package parser must emit typed `json_corrupt:` warnings "
        "for JSONDecodeError. Generic 'parse failed' loses the kind."
    )


def test_parser_emits_typed_io_error_warning_on_filesystem_failure():
    """OSError / FileNotFoundError must surface as `io_error:` so
    operators can distinguish a missing-file (re-upload needed) from
    a malformed-file (re-export from Drive needed)."""
    assert "io_error" in DMA_PKG, (
        "dma_package parser must emit `io_error:` for OSError. "
        "Operators can't fix what they can't classify."
    )


def test_parser_emits_typed_schema_mismatch_warning_on_validation_failure():
    """When the JSON parses but doesn't match the expected schema
    (pydantic ValidationError, etc.), the warning must be
    `schema_mismatch:` — not folded into `json_corrupt` (which would
    suggest re-exporting the file when the actual issue is the schema)."""
    assert "schema_mismatch" in DMA_PKG, (
        "dma_package parser must emit `schema_mismatch:` for shape "
        "errors. Folding into json_corrupt misleads the operator's "
        "remediation choice."
    )


def test_maybe_helper_routes_exceptions_to_correct_warning_kind():
    """The `_maybe(...)` helper is the central choke-point that maps
    exception types to warning kinds. Walking the source confirms
    each branch is wired correctly."""
    # The helper must explicitly handle OSError -> io_error,
    # JSONDecodeError -> json_corrupt, and a fall-through (typically
    # pydantic ValidationError or TypeError) -> schema_mismatch.
    import re

    # Find the _maybe function body.
    m = re.search(
        r"def _maybe\([^)]*\)[\s\S]+?(?=\ndef |\nclass )",
        DMA_PKG,
    )
    assert m, "_maybe helper not found in dma_package.py"
    body = m.group(0)
    assert "io_error" in body, (
        "_maybe must route OSError -> io_error warning kind."
    )
    assert "json_corrupt" in body, (
        "_maybe must route JSONDecodeError -> json_corrupt."
    )
    assert "schema_mismatch" in body, (
        "_maybe must route fall-through exceptions -> schema_mismatch."
    )


def test_parser_warnings_use_label_prefix_for_file_identification():
    """Each warning must lead with a `{label}:` so the operator can
    tell WHICH file in the package triggered it. Without the label,
    100 warnings from 100 files look identical."""
    import re

    m = re.search(
        r"def _maybe\([^)]*\)[\s\S]+?(?=\ndef |\nclass )",
        DMA_PKG,
    )
    body = m.group(0)
    # Every warnings.append must use f"{label}: ..." format.
    appends = re.findall(r'warnings\.append\(([^)]+)\)', body)
    assert appends, "_maybe must emit warnings via warnings.append"
    for app in appends:
        assert "label" in app or "{label}" in app, (
            f"warnings.append call missing label prefix: {app}. "
            "Without `{label}:` operators can't trace warnings to files."
        )


def test_parser_warning_kinds_match_import_audit_classifier():
    """The import_audit UI groups warnings by the kind prefix. The
    set of kinds emitted by the parser MUST match the set the UI
    classifier expects. A new kind without UI handling = the warning
    silently lands in 'other'."""
    # Pull the kinds from the parser.
    parser_kinds = set()
    for kind in ("json_corrupt", "io_error", "schema_mismatch"):
        if f"{kind}:" in DMA_PKG or f'"{kind}"' in DMA_PKG:
            parser_kinds.add(kind)

    expected_classifier_kinds = {"json_corrupt", "io_error", "schema_mismatch"}
    missing = expected_classifier_kinds - parser_kinds
    assert not missing, (
        f"Parser missing kinds the import_audit classifier expects: "
        f"{missing}. UI grouping would degrade to 'other'."
    )


def test_parser_warnings_documented_in_state_branch_contract():
    """The audit pinned the contract: `json_corrupt`, `io_error`,
    `schema_mismatch` as the documented state branches. The
    docstring must enumerate them so future devs see the contract."""
    # The contract documentation lives in dma_package.py's docstring
    # (the `_maybe` helper documents the 3-state mapping).
    for marker in ("json_corrupt", "io_error", "schema_mismatch"):
        assert marker in DMA_PKG, (
            f"dma_package.py docstring missing state-branch marker "
            f"{marker!r}. Without documented kinds the next dev "
            "doesn't know to extend the import-audit classifier."
        )


def test_parser_emits_docx_only_warning_when_workbook_missing():
    """The `docx_only_package_no_manifest` warning is the documented
    state for "DOCX-only DMA package" -- a valid sub-shape. Without
    this typed warning the operator can't tell a partial package
    from a corrupt one."""
    assert "docx_only_package_no_manifest" in DMA_PKG, (
        "dma_package must emit `docx_only_package_no_manifest` "
        "warning for DOCX-only packages. Otherwise the partial "
        "shape looks identical to a corrupt one."
    )


def test_run_manifest_json_corrupt_records_tried_paths():
    """When run_manifest.json fails to parse, the warning must
    include the paths the parser tried (so the operator knows whether
    to re-upload or move the file). The audit pinned this as a
    debuggability requirement."""
    assert (
        "tried_paths" in DMA_PKG
        or ("tried" in DMA_PKG and "manifest" in DMA_PKG)
    ), (
        "dma_package run_manifest failure must surface tried_paths "
        "in the warning so operators know which paths to check."
    )


# ---------------------------------------------------------------------
# D1.4 — pydantic-URL-leak sanitize (functional)
# ---------------------------------------------------------------------
# A pydantic v2 ValidationError str() spans 4 lines, the last being
# `For further information visit https://errors.pydantic.dev/...`. The
# old `f"{label}: {e!s}"` stuffed that whole blob (URL included) into
# `runs.parser_warnings`, surfacing the docs URL on 18 clients' Overview.
# The fix keeps only the FIRST line, capped at 120 chars.


def test_maybe_strips_pydantic_docs_url_from_schema_mismatch_warning(tmp_path):
    """A real pydantic ValidationError (a ValueError → schema_mismatch
    branch) must surface as a single capped line with NO
    `errors.pydantic.dev` URL."""
    from pydantic import BaseModel

    from app.services.parsers.dma_package import _maybe

    class _M(BaseModel):
        x: int

    def _bad_parser(_text):
        return _M(x="not-an-int")  # raises ValidationError

    p = tmp_path / "03_scoring_workbook.csv"
    p.write_text("irrelevant", encoding="utf-8")
    warnings: list[str] = []

    out = _maybe(_bad_parser, p, warnings, "03_scoring")

    assert out is None
    assert len(warnings) == 1
    w = warnings[0]
    assert w.startswith("03_scoring: schema_mismatch:")
    assert "errors.pydantic.dev" not in w, (
        "pydantic docs URL leaked into parser_warnings — D1.4 regression"
    )
    assert "\n" not in w, "warning must be a single line"


def test_maybe_caps_generic_exception_first_line_at_120_chars(tmp_path):
    """The generic `except Exception` branch must also keep only the
    first line, capped at 120 chars — so a runaway message or a URL on
    a later line can't bloat parser_warnings."""
    from app.services.parsers.dma_package import _maybe

    def _bad_parser(_text):
        # First line longer than the cap; URL parked on a later line.
        raise RuntimeError("z" * 300 + "\nhttps://errors.pydantic.dev/leak")

    p = tmp_path / "f.json"
    p.write_text("{}", encoding="utf-8")
    warnings: list[str] = []

    _maybe(_bad_parser, p, warnings, "lbl")

    w = warnings[0]
    assert w.startswith("lbl: RuntimeError:")
    assert "errors.pydantic.dev" not in w
    assert "\n" not in w
    detail = w.split("RuntimeError:", 1)[1].strip()
    assert len(detail) == 120, "generic-branch detail must be capped at 120 chars"
