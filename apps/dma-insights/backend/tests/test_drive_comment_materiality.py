"""Comment materiality classifier — Batch 9 contract test.

Per the integrated batched plan: pin the keyword matrix, the
aggregation semantics, and the Drive extractor's response-shape
assumptions. Planted comments cover the material keyword groups
(rescore / data_quality / maintenance / evidence / taxonomy /
narrative) and the cosmetic chatter tokens.

No skips: the Drive client is a hand-rolled stub so tests run
without network OR GCP creds. Per the operator mandate, every
defensive branch is exercised (empty body, exception during fetch,
mixed material+cosmetic in one record, etc.).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.services.drive_comment_materiality import (
    MATERIAL_KEYWORDS,
    CommentClassification,
    CommentRecord,
    build_observation_payload,
    classify_comment_body,
    classify_comments,
    extract_comment_records,
)

# ── classify_comment_body ────────────────────────────────────────────


@pytest.mark.parametrize("body,group", [
    ("Please re-score P3C2 — the workbook overshoots", "rescore"),
    ("This needs a rescore", "rescore"),
    ("Re-rate the platform card",  "rescore"),
    ("Their score looks off",  "rescore"),
    ("This score is wrong",  "data_quality"),
    ("The percentage is incorrect",  "data_quality"),
    ("There's an error in the heatmap",  "data_quality"),
    ("Hallucinated citation — E-9999 doesn't exist",  "data_quality"),
    ("Fix the cell color encoding",  "maintenance"),
    ("This is broken — page 502s on load",  "maintenance"),
    ("Needs update to v7 catalogue",  "maintenance"),
    ("Please regenerate the SCQA",  "maintenance"),
    ("No evidence backing this rating",  "evidence"),
    ("Missing evidence anchor",  "evidence"),
    ("Where is the source for this number?",  "evidence"),
    ("Wrong subcap — should be P1C2.1.1 not P1C2.1.2",  "taxonomy"),
    ("Mislabeled finding",  "taxonomy"),
    ("Please rewrite this paragraph",  "narrative"),
    ("Needs revising",  "narrative"),
    ("Incomplete — missing context",  "narrative"),
])
def test_material_comments_are_classified_material(body: str, group: str) -> None:
    out = classify_comment_body(body)
    assert out.label == "material", (
        f"body={body!r} expected MATERIAL but got {out}"
    )
    assert out.reason.startswith(f"matched:{group}:"), (
        f"expected matched group {group}; got {out.reason}"
    )


@pytest.mark.parametrize("body", [
    "+1",
    "thx",
    "Thanks!",
    "LGTM",
    "Looks good to me",
    "Looks great, nice work",
    "approved",
    "noted",
    "FYI — sharing with the team",
])
def test_cosmetic_chatter_is_classified_cosmetic(body: str) -> None:
    out = classify_comment_body(body)
    assert out.label == "cosmetic", f"body={body!r} expected COSMETIC; got {out}"
    assert out.reason.startswith("chatter:"), out.reason


@pytest.mark.parametrize("body", [
    "Saw the deck draft yesterday",
    "I'll loop back with the team next week",
    "Sharing this internally",
])
def test_neutral_chatter_is_classified_cosmetic_no_signal(body: str) -> None:
    out = classify_comment_body(body)
    assert out.label == "cosmetic"
    assert out.reason == "no_signal"


def test_empty_body_falls_back_to_material() -> None:
    """Defense-in-depth: empty/whitespace/None body must NOT silently
    skip. The classifier returns MATERIAL so the re-ingest path fires
    and the operator can audit the empty comment manually."""
    for b in [None, "", "   ", "\t\n", " \n\t "]:
        out = classify_comment_body(b)
        assert out.label == "material", f"empty {b!r} should fall back to material"
        assert out.reason == "empty_body:fallback_material"


def test_material_keyword_wins_over_cosmetic_chatter_in_same_comment() -> None:
    """A comment "Looks good but also re-score P3C2" must classify
    MATERIAL — the chatter signal must NOT mask the action signal."""
    out = classify_comment_body(
        "Looks good but also re-score P3C2 — the workbook overshoots"
    )
    assert out.label == "material"
    assert out.reason.startswith("matched:rescore:")


def test_word_boundary_prevents_false_match() -> None:
    """Material keywords must word-boundary match — 'fix' must not
    trigger on 'affix', 'prefix', 'fixture'. 'error' must not trigger
    on 'mirroring'."""
    for b in [
        "We'll affix the label to the deck",
        "Prefix the section with the run id",
        "The fixture covers this case",
        "Mirroring the workbook into the report",
        "All our updaters are async",  # 'update' is not standalone here
    ]:
        out = classify_comment_body(b)
        if out.label == "material":
            # The 'updaters' case actually contains 'update' as a
            # prefix — word boundary should reject it. Document any
            # surprise here as a regression.
            pytest.fail(
                f"word-boundary failure: {b!r} → {out.reason}"
            )


def test_case_insensitive_match() -> None:
    for b in ["RE-SCORE this finding", "rescore!", "RESCORE", "Rescore?"]:
        out = classify_comment_body(b)
        assert out.label == "material", b


def test_unicode_body_does_not_crash() -> None:
    out = classify_comment_body("Élève la note — re-score s'il vous plaît")
    assert out.label == "material"
    assert "rescore" in out.reason


def test_classification_returns_dataclass_with_expected_shape() -> None:
    out = classify_comment_body("fix this")
    assert isinstance(out, CommentClassification)
    assert out.label in {"material", "cosmetic"}
    assert isinstance(out.reason, str)


def test_all_keyword_groups_have_at_least_one_pattern() -> None:
    """Defense against accidentally emptying a keyword group."""
    for group, phrases in MATERIAL_KEYWORDS.items():
        assert phrases, f"keyword group {group!r} is empty"
        for p in phrases:
            assert p.strip(), f"empty phrase in group {group}"


# ── classify_comments aggregator ─────────────────────────────────────


def _rec(body: str, dt: datetime | None = None) -> CommentRecord:
    return CommentRecord(
        file_id="f1",
        comment_id="c1",
        body=body,
        modified_time=dt,
    )


def test_aggregate_counts_material_and_cosmetic() -> None:
    recs = [
        _rec("re-score P3C2"),
        _rec("Looks good!"),
        _rec("fix this"),
        _rec("thx"),
        _rec("nice work"),
    ]
    s = classify_comments(recs)
    assert s.material_count == 2
    assert s.cosmetic_count == 3
    assert s.empty_count == 0
    assert s.has_material()
    assert not s.has_only_cosmetic()


def test_aggregate_returns_only_cosmetic_when_all_chatter() -> None:
    recs = [_rec("+1"), _rec("LGTM"), _rec("noted")]
    s = classify_comments(recs)
    assert s.material_count == 0
    assert s.cosmetic_count == 3
    assert s.has_only_cosmetic()
    assert not s.has_material()


def test_aggregate_tracks_latest_timestamps_per_class() -> None:
    a = datetime(2026, 6, 1, tzinfo=UTC)
    b = datetime(2026, 6, 2, tzinfo=UTC)
    c = datetime(2026, 6, 3, tzinfo=UTC)
    recs = [
        _rec("re-score this", a),
        _rec("re-score that", c),  # latest material
        _rec("LGTM", b),
    ]
    s = classify_comments(recs)
    assert s.latest_material_at == c
    assert s.latest_cosmetic_at == b
    assert s.latest_change_at == c


def test_aggregate_latest_change_handles_only_cosmetic_present() -> None:
    a = datetime(2026, 6, 1, tzinfo=UTC)
    s = classify_comments([_rec("thx", a)])
    assert s.latest_change_at == a
    assert s.latest_material_at is None
    assert s.latest_cosmetic_at == a


def test_aggregate_samples_truncated_to_three() -> None:
    recs = [_rec(f"please re-score finding {i}") for i in range(10)]
    s = classify_comments(recs)
    assert len(s.sample_material) == 3


def test_aggregate_empty_body_increments_material_and_empty() -> None:
    """An empty body is a MATERIAL classification (fallback) AND is
    tracked separately so the operator can audit."""
    s = classify_comments([_rec(""), _rec("   ")])
    assert s.material_count == 2
    assert s.empty_count == 2
    assert s.cosmetic_count == 0
    # has_only_cosmetic must reject because empty_count > 0 — the
    # operator should look at empty bodies before treating them as
    # noise.
    assert not s.has_only_cosmetic()


def test_aggregate_empty_records_is_no_op() -> None:
    s = classify_comments([])
    assert s.material_count == 0
    assert s.cosmetic_count == 0
    assert s.latest_change_at is None
    assert not s.has_material()
    assert not s.has_only_cosmetic()


# ── extract_comment_records ──────────────────────────────────────────


class _FakeDrive:
    """Minimal duck-typed Drive v3 service for the classifier extractor.

    The Drive client builds responses like
    ``drive.comments().list(fileId=..., fields=..., pageSize=...).execute()``.
    This stub returns canned per-file responses and tracks each call so
    the test can assert the extractor passes the expected fields.
    """

    def __init__(self, per_file: dict[str, dict], raise_on: set[str] | None = None):
        self._per_file = per_file
        self._raise_on = raise_on or set()
        self.calls: list[dict] = []

    def comments(self):
        return _CommentsFacade(self)


class _CommentsFacade:
    def __init__(self, drive: _FakeDrive):
        self._drive = drive

    def list(self, *, fileId: str, fields: str, pageSize: int):
        self._drive.calls.append(
            {"fileId": fileId, "fields": fields, "pageSize": pageSize}
        )
        return _ListRequest(self._drive, fileId)


class _ListRequest:
    def __init__(self, drive: _FakeDrive, file_id: str):
        self._drive = drive
        self._file_id = file_id

    def execute(self) -> dict[str, Any]:
        if self._file_id in self._drive._raise_on:
            raise RuntimeError(f"drive 503 on {self._file_id}")
        return self._drive._per_file.get(self._file_id, {"comments": []})


def test_extract_records_basic_shape() -> None:
    drive = _FakeDrive({
        "file-A": {
            "comments": [
                {
                    "id": "c1",
                    "content": "re-score P3C2",
                    "modifiedTime": "2026-06-01T10:00:00Z",
                    "resolved": False,
                    "author": {"displayName": "Reviewer X"},
                },
                {
                    "id": "c2",
                    "content": "+1",
                    "modifiedTime": "2026-06-02T09:00:00Z",
                    "resolved": True,
                    "author": {"displayName": "AE Y"},
                },
            ]
        },
        "file-B": {"comments": []},
    })
    recs = extract_comment_records(drive, ["file-A", "file-B"])
    assert len(recs) == 2
    assert {r.comment_id for r in recs} == {"c1", "c2"}
    by_id = {r.comment_id: r for r in recs}
    assert by_id["c1"].body == "re-score P3C2"
    assert by_id["c1"].modified_time == datetime(2026, 6, 1, 10, tzinfo=UTC)
    assert by_id["c1"].resolved is False
    assert by_id["c1"].author_name == "Reviewer X"
    assert by_id["c2"].resolved is True


def test_extract_records_passes_correct_drive_fields() -> None:
    drive = _FakeDrive({"x": {"comments": []}})
    extract_comment_records(drive, ["x"])
    assert drive.calls[0]["fields"].startswith("comments(")
    # The classifier needs the content field — verify it's being asked
    # for, since the legacy probe only asked for modifiedTime,resolved.
    assert "content" in drive.calls[0]["fields"]
    assert "modifiedTime" in drive.calls[0]["fields"]


def test_extract_records_swallows_per_file_drive_error() -> None:
    """A 503 on one file MUST NOT abort the whole probe — other files
    continue to be scanned."""
    drive = _FakeDrive(
        per_file={
            "ok-file": {
                "comments": [{
                    "id": "c1", "content": "fix this",
                    "modifiedTime": "2026-06-01T10:00:00Z",
                }]
            },
        },
        raise_on={"bad-file"},
    )
    recs = extract_comment_records(drive, ["bad-file", "ok-file"])
    assert len(recs) == 1
    assert recs[0].file_id == "ok-file"


def test_extract_records_handles_invalid_modified_time() -> None:
    drive = _FakeDrive({
        "f": {"comments": [
            {"id": "c1", "content": "fix this", "modifiedTime": "not-a-date"},
            {"id": "c2", "content": "+1"},  # missing modifiedTime
        ]}
    })
    recs = extract_comment_records(drive, ["f"])
    assert len(recs) == 2
    assert recs[0].modified_time is None
    assert recs[1].modified_time is None


def test_extract_records_bounded_by_file_limit() -> None:
    drive = _FakeDrive({})
    extract_comment_records(drive, [f"file-{i}" for i in range(100)], file_limit=5)
    assert len(drive.calls) == 5


def test_extract_records_empty_input_no_call() -> None:
    drive = _FakeDrive({})
    recs = extract_comment_records(drive, [])
    assert recs == []
    assert drive.calls == []


# ── observation payload ──────────────────────────────────────────────


def test_observation_payload_is_json_safe() -> None:
    import json as _json
    a = datetime(2026, 6, 1, 12, tzinfo=UTC)
    s = classify_comments([
        _rec("re-score this", a),
        _rec("LGTM", a),
    ])
    payload = build_observation_payload(
        s,
        folder_name="Test Bank - DMA",
        prior_completed_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    assert payload["kind"] == "drive_comment_classification"
    assert payload["material_count"] == 1
    assert payload["cosmetic_count"] == 1
    assert payload["folder_name"] == "Test Bank - DMA"
    # Round-trips through JSON without TypeError.
    _json.dumps(payload)


def test_observation_payload_handles_no_records() -> None:
    s = classify_comments([])
    payload = build_observation_payload(
        s,
        folder_name="Empty Folder",
        prior_completed_at=None,
    )
    assert payload["material_count"] == 0
    assert payload["latest_material_at"] is None
    assert payload["prior_completed_at"] is None
