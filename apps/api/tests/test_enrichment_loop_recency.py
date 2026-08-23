"""A health check with no recency term reports the last good run forever.

MEM-0102: GET /v1/ops/enrichment-loop returned healthy:true while the
dmai-enrich-loop trigger had not fired in about five days. Every clause of the
verdict was about WHAT the last job did — did it finish, did it error, did it
scan anything — and none was about WHEN. So a loop that stopped entirely
stayed green on the strength of the last run it ever managed.

The endpoint's own docstring already had the right instinct: "a loop that
finds nothing to look at reports the same numbers as a loop with nothing to
do, and only one of those is fine." A loop that has not run at all reports the
same numbers as both.
"""
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dma_api.main import _age_seconds  # noqa: E402


def _ago(**kw):
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(**kw)


def test_age_of_a_recent_job():
    assert 0 <= _age_seconds(_ago(minutes=10)) <= 700


def test_age_of_a_five_day_old_job():
    """The measured case: five days against an hourly trigger."""
    age = _age_seconds(_ago(days=5))
    assert age > 4 * 24 * 3600
    assert age // 3600 >= 120


def test_a_naive_timestamp_is_read_as_utc():
    """Postgres hands back naive datetimes on some drivers. Treating one as
    local time would shift the age by the container's offset."""
    naive = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    assert abs(_age_seconds(naive)) < 120


def test_an_iso_string_is_accepted():
    assert _age_seconds(_ago(hours=2).isoformat()) > 7000


@pytest.mark.parametrize("bad", [None, "not-a-date", 42, object()])
def test_an_unmeasurable_age_is_none_never_zero(bad):
    """THE DANGEROUS DIRECTION. None means unknown; 0 means "just now". A
    missing timestamp that read as 0 would report a dead loop as healthy,
    which is the defect this helper exists to end."""
    assert _age_seconds(bad) is None


def test_the_endpoint_takes_a_stale_window_and_reports_the_age():
    """Ops widens the window deliberately, not by editing the file — and the
    age is reported whether or not it trips, so a reader can judge the cadence
    rather than trust this endpoint's arithmetic about it."""
    src = (Path(__file__).resolve().parents[1] / "dma_api" / "main.py").read_text()
    assert "stale_after_hours: int = 3" in src
    assert '"last_job_age_seconds": age' in src
    assert "and not stale" in src, "staleness must join the healthy conjunction"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
