"""Promote refuses when the deployed connector is behind the repository's gates.

MEM-0039 (an API revision built five hours before the commit it was assumed
to carry) and MEM-0562 (SWBC nearly re-promoted against a production API
missing the redaction fixes it had been remediated for): "fixed" was asserted
from the repository while production ran a different copy, and nothing
compared the two before a promote. MEM-0562's fix_hint names the half still
unbuilt: a promote-time comparison of the serving revision against HEAD.

The connector cannot see the repository. So the caller states what its gates
assume — `promote_checks.local_revision(repo)`: the contract digest, the gold
digest and the gate-set digest — and the connector compares that with what
it is actually running. A mismatch refuses before anything is read. With no
expected revision the result RECORDS the check as unchecked; it is never
reported as matched.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _promote_fake import RUN, Conn, skeleton, wrote_anything  # noqa: E402

from dma_mcp.promote import promote_run  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]


def _pc():
    """Imported per test so the promote-driven cases run (and fail on their
    assertions) against a connector that predates the module."""
    from dma_mcp import promote_checks
    return promote_checks


def test_a_connector_behind_the_repository_refuses():
    want = _pc().local_revision(ROOT)
    want["contract_version"] = "cr-000000000000"     # the repo moved on
    conn = Conn(skeleton())
    out = promote_run(conn, RUN, expected_revision=want)
    assert out["promoted"] is False
    assert out["error"] == "deployed_revision_behind"
    assert "contract_version" in out["mismatch"]
    assert not wrote_anything(conn)
    assert not any("FROM submissions" in s for s in conn.cur.sql), \
        "the revision refusal comes before the run's pages are even read"


def test_the_same_revision_promotes_and_says_it_matched():
    out = promote_run(Conn(skeleton()), RUN,
                      expected_revision=_pc().local_revision(ROOT))
    assert out["promoted"] is True, out
    assert out["revision_check"].startswith("matched")


def test_without_an_expected_revision_it_is_recorded_unchecked():
    out = promote_run(Conn(skeleton()), RUN)
    assert out["promoted"] is True
    assert out["revision_check"].startswith("unchecked")
    assert out["deployed_revision"]["contract_version"].startswith("cr-")


def test_a_field_this_deployment_does_not_expose_is_unchecked_not_matched(
        monkeypatch):
    monkeypatch.delenv("DMA_SOURCE_SHA", raising=False)
    want = {**_pc().local_revision(ROOT), "source_sha": "abc123"}
    out = promote_run(Conn(skeleton()), RUN, expected_revision=want)
    assert out["promoted"] is True
    assert "unchecked" in out["revision_check"]
    assert "source_sha" in out["revision_check"]


def test_local_and_deployed_fingerprints_agree_on_one_checkout():
    """The two functions must compute the same thing, or every promote from
    a current checkout would refuse."""
    local = _pc().local_revision(ROOT)
    deployed = _pc().deployed_revision()
    for key in local:
        assert local[key] == deployed[key], key
