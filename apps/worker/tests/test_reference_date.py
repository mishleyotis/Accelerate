"""`reference_date` — the field the whole recency ladder hangs from.

`runs.completed_at` becomes every evidence row's `reference_date`, and the
GENERATED `age_months` and `recency_band` are NULL / UNVERIFIED without it.
Baxter's manifest stated no date, so all 120 served items banded UNVERIFIED —
including 45 that carried a published_date — and a FACT rendered beside an
"unverified" label. The date was in the run's own request id all along.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.persist import _request_id_date, _stated_completed_at  # noqa: E402


def test_a_stated_manifest_date_still_wins():
    # The request id is a LAST resort, never a substitute for a stated field.
    m = {"assessment": {"date": "2026-03-30"},
         "run_id": "DMA-ASM-BCU-20250101-0001"}
    assert _stated_completed_at(m) == "2026-03-30"


def test_the_request_id_date_is_read_when_the_manifest_is_silent():
    assert _stated_completed_at({"run_id": "DMA-ASM-BCU-20260330-0001"}) == "2026-03-30"


def test_every_manifest_key_variant_is_still_honoured():
    for k in ("assessment_date", "completed_at", "generated_at",
              "execution_timestamp", "last_updated"):
        assert _stated_completed_at({k: "2024-07-01T09:00:00Z"}).startswith("2024-07-01")


def test_an_impossible_date_in_the_id_yields_null_not_a_bad_string():
    # A DATE column would reject "2026-13-45" and abort the whole package.
    assert _request_id_date({"run_id": "DMA-ASM-BCU-20261345-0001"}) is None
    assert _request_id_date({"run_id": "DMA-ASM-BCU-20260230-0001"}) is None


def test_a_request_id_with_no_date_token_yields_null():
    for rid in ("DMA-ASM-BCU-0001", "", "not-an-id", "DMA-ASM-BCU-2026-0001"):
        assert _request_id_date({"run_id": rid}) is None


def test_nothing_stated_anywhere_stays_null():
    # Computed or null (invariant 9). No scan-date substitute that looks like
    # the assessment's own date.
    assert _stated_completed_at({}) is None
    assert _stated_completed_at({"assessment_date": "March 2026"}) is None


def test_the_token_is_taken_from_the_END_of_the_id():
    # An entity token that happens to contain eight digits must not be mistaken
    # for the date; the date is the second-to-last dash-delimited group.
    assert _request_id_date(
        {"run_id": "DMA-ASM-12345678-20260330-0002"}) == "2026-03-30"
