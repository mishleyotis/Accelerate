"""Run-ID normalizer covers both `REQ-{8 hex}` and `DMA-ASM-…` forms."""
from __future__ import annotations

import pytest

from app.services.parsers.run_id import is_valid_run_id, parse_run_id


def test_req_form_parses() -> None:
    info = parse_run_id("REQ-A6654887")
    assert info.kind == "REQ"
    assert info.is_canonical is True
    assert info.entity_token is None


def test_dma_asm_parses() -> None:
    info = parse_run_id("DMA-ASM-ALMA-20260519-0001")
    assert info.kind == "ASM"
    assert info.entity_token == "ALMA"
    assert info.date_iso == "2026-05-19"
    assert info.seq == 1
    assert info.is_canonical is False


def test_dma_res_parses() -> None:
    info = parse_run_id("DMA-RES-WSFS-20260519-0001")
    assert info.kind == "RES"
    assert info.entity_token == "WSFS"


def test_invalid_format_raises() -> None:
    with pytest.raises(ValueError):
        parse_run_id("not-a-run-id")
    with pytest.raises(ValueError):
        parse_run_id("REQ-toolong0123")
    with pytest.raises(ValueError):
        parse_run_id("DMA-ASM-X-bad-0001")


def test_invalid_date_in_dma_asm_raises() -> None:
    with pytest.raises(ValueError):
        parse_run_id("DMA-ASM-X-20261332-0001")


def test_is_valid_helper() -> None:
    assert is_valid_run_id("REQ-A6654887") is True
    assert is_valid_run_id("DMA-ASM-WSFS-20260519-0001") is True
    assert is_valid_run_id("bogus") is False


# ── compute_assessment_date (migration 039 fallback chain) ───────────

def test_assessment_date_prefers_run_manifest() -> None:
    from datetime import date

    from app.services.parsers.run_id import compute_assessment_date
    got, src = compute_assessment_date(
        date(2026, 5, 1), "DMA-ASM-ALMA-20260519-0001", date(2026, 6, 1),
    )
    assert got == date(2026, 5, 1)
    assert src == "run_manifest"


def test_assessment_date_falls_back_to_run_id_segment() -> None:
    from datetime import date

    from app.services.parsers.run_id import compute_assessment_date
    got, src = compute_assessment_date(
        None, "DMA-ASM-ALMA-20260519-0001", date(2026, 6, 1),
    )
    assert got == date(2026, 5, 19)
    assert src == "run_id"


def test_assessment_date_req_hex_uses_package_date() -> None:
    from datetime import date

    from app.services.parsers.run_id import compute_assessment_date
    got, src = compute_assessment_date(None, "REQ-A6654887", date(2026, 6, 1))
    assert got == date(2026, 6, 1)
    assert src == "package_manifest"


def test_assessment_date_nothing_available() -> None:
    from app.services.parsers.run_id import compute_assessment_date
    got, src = compute_assessment_date(None, "REQ-A6654887", None)
    assert got is None
    assert src is None


def test_assessment_date_synth_id_tolerated() -> None:
    # Synthesized manifests carry SYNTH-{hex} ids — unparseable by
    # parse_run_id; the helper must swallow the ValueError, not raise.
    from app.services.parsers.run_id import compute_assessment_date
    got, src = compute_assessment_date(None, "SYNTH-E153A04B0A80", None)
    assert got is None and src is None
