"""`drive_get` used to answer a permissions failure with `{"error": {...}}`,
and every caller read that with `.get("files", [])`. A folder the routine
could not read and a folder with nothing in it produced the same `[]`, so the
preflight printed "readable but empty — nothing to scan" and the routine
stopped. That is the one silent failure that looks like success.
"""
import io
import json
import urllib.error

import pytest

import routine_secrets as R

INTAKE = "1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo"
STORED_KEY_SA = "dma-routine@digital-maturity-assessor.iam.gserviceaccount.com"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(R, "drive_token", lambda *a, **k: ("tok", "test"))
    monkeypatch.setattr(R, "_DRIVE_IDENTITY", STORED_KEY_SA, raising=False)
    monkeypatch.setattr(R, "doc_secrets", dict)
    # The secrets doc became an input to main()'s verdict on 2026-08-14. These
    # tests are about the intake TREE, so the doc is held green here for the
    # same reason the Drive layer is: an assertion about the tree only means
    # something when the tree is the sole thing that can have moved. The two
    # tests that failed when the doc check landed were reading its FAIL as a
    # tree result. raising=False so this file still runs against a module
    # predating either function.
    monkeypatch.setattr(R, "doc_status",
                        lambda: {"ok": True, "keys": 2, "reason": ""},
                        raising=False)
    monkeypatch.setattr(R, "credential_provenance",
                        lambda: {"DMA_ROUTINE_GITHUB_PAT": "secrets doc",
                                 "DMA_ROUTINE_DRIVE_SA_KEY": "secrets doc"},
                        raising=False)
    monkeypatch.setattr(R, "github_pat", lambda: "irrelevant-here")
    # raising=False so the semantic tests below fail on BEHAVIOUR against a
    # module that has no PAT check at all, rather than on the patch.
    monkeypatch.setattr(R, "github_pat_status",
                        lambda *a, **k: {"ok": True, "verdict": "OK",
                                         "detail": "stubbed"}, raising=False)


def _drive(monkeypatch, code=None, payload=None):
    def fake(req, *a, **kw):
        if code:
            raise urllib.error.HTTPError(req.full_url, code, "no", {},
                                         io.BytesIO(b"forbidden"))
        return _Resp(json.dumps(payload or {}).encode())

    monkeypatch.setattr(R.urllib.request, "urlopen", fake)


def test_a_drive_error_raises_instead_of_answering(monkeypatch):
    _drive(monkeypatch, code=404)
    with pytest.raises(R.DriveError) as ei:
        R.drive_get(f"files/{INTAKE}", fields="id,name")
    assert ei.value.code == 404


def test_a_drive_error_can_never_be_read_as_an_empty_listing(monkeypatch):
    """The exact expression that produced the silent failure."""
    _drive(monkeypatch, code=403)
    with pytest.raises(R.DriveError):
        R.drive_get("files", q=f"'{INTAKE}' in parents").get("files", [])


def test_a_transport_failure_is_also_not_an_empty_listing(monkeypatch):
    def boom(req, *a, **kw):
        raise urllib.error.URLError("connection reset")

    monkeypatch.setattr(R.urllib.request, "urlopen", boom)
    with pytest.raises(R.DriveError):
        R.drive_get("files", q="x")


def test_a_genuinely_empty_folder_still_reads_as_empty(monkeypatch):
    _drive(monkeypatch, payload={"files": []})
    assert R.drive_get("files", q="x")["files"] == []


def test_main_fails_when_the_tree_cannot_be_read(monkeypatch, capsys):
    _drive(monkeypatch, code=404)
    assert R.main() == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "nothing to scan" not in out, "an unreadable tree reported as empty"
    assert "empty" not in out.replace("not the same as the tree being empty", "")


def test_an_unreadable_child_listing_is_not_reported_as_nothing_to_scan(
        monkeypatch, capsys):
    """The precise measured shape: the folder resolves, listing its children
    fails, and the old code printed 'readable but empty — nothing to scan',
    which the routine's instructions treat as 'stop, there is no work'."""
    calls = []

    def fake(req, *a, **kw):
        calls.append(req.full_url)
        if len(calls) == 1:
            return _Resp(json.dumps({"id": INTAKE, "name": "General DMAs"}).encode())
        raise urllib.error.HTTPError(req.full_url, 403, "no", {},
                                     io.BytesIO(b"forbidden"))

    monkeypatch.setattr(R.urllib.request, "urlopen", fake)
    rc = R.main()
    out = capsys.readouterr().out
    assert "nothing to scan" not in out, out
    assert "readable but empty" not in out, out
    assert rc == 1, "an unreadable listing did not stop the routine"


def test_main_warns_but_does_not_fail_on_a_genuinely_empty_tree(monkeypatch,
                                                                capsys):
    calls = []

    def fake(req, *a, **kw):
        calls.append(req.full_url)
        body = ({"id": INTAKE, "name": "General DMAs"} if len(calls) == 1
                else {"files": []})
        return _Resp(json.dumps(body).encode())

    monkeypatch.setattr(R.urllib.request, "urlopen", fake)
    assert R.main() == 2                      # WARN: degraded but workable
    out = capsys.readouterr().out
    assert "genuinely empty" in out


def test_main_passes_when_the_tree_has_children(monkeypatch):
    calls = []

    def fake(req, *a, **kw):
        calls.append(req.full_url)
        body = ({"id": INTAKE, "name": "General DMAs"} if len(calls) == 1
                else {"files": [{"id": "a", "name": "Baxter Credit Union"}]})
        return _Resp(json.dumps(body).encode())

    monkeypatch.setattr(R.urllib.request, "urlopen", fake)
    assert R.main() == 0


def test_remediation_names_the_identity_that_took_the_404(monkeypatch, capsys):
    """A 404 incurred by the STORED KEY told the operator to share the folder
    with dmai-worker@, which already had access — a wasted action."""
    _drive(monkeypatch, code=404)
    R.main()
    out = capsys.readouterr().out
    assert STORED_KEY_SA in out, "did not name the identity that actually failed"


def test_main_fails_when_the_pat_check_fails(monkeypatch, capsys):
    monkeypatch.setattr(R, "github_pat_status",
                        lambda *a, **k: {"ok": False, "verdict": "FAIL",
                                         "detail": "EXPIRED at some time"})
    assert R.main() == 1
    assert "FAIL" in capsys.readouterr().out
