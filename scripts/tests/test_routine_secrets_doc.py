"""The preflight read the secrets doc and then graded the run without it.

`main()` called `doc_secrets()` for the line it printed and discarded the
return value. Nothing downstream consulted it. So a doc that 404'd printed

    secrets doc         FAIL  404: the doc is not shared with …

and `main()` returned 0 regardless, and `routine_preflight.sh` mapped exit 0
to `secrets OK` and then to `PREFLIGHT PASS — proceed`. The composite verdict
was computed without its own most important input, with the contradicting
evidence printed two lines above it.

A doc that parsed to zero keys was worse: every transport check passed, so it
printed **OK** on zero credentials.

Each test below is the negative control for one of those paths — it fails
against the pre-2026-08-14 `main()` and passes against the repaired one. The
last two pin the properties that must survive the repair: the escape hatch
stays deliberate, and no verdict line ever carries a value.
"""
import os

import pytest

import routine_secrets as R

DOC_KEYS = {"DMA_ROUTINE_GITHUB_PAT": "github_pat_" + "x" * 71,
            "DMA_ROUTINE_DRIVE_SA_KEY": '{"type": "service_account"}'}


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Everything main() touches after the doc, stubbed green.

    The point of every test here is that the DOC decides the outcome, so all
    the other inputs are held at pass. If a test fails, the doc is the only
    thing that can have caused it.
    """
    monkeypatch.setattr(R, "_DOC_CACHE", None, raising=False)
    monkeypatch.setattr(R, "_DOC_STATUS", None, raising=False)
    monkeypatch.setattr(R, "github_pat_status",
                        lambda *a, **k: {"ok": True, "verdict": "OK",
                                         "detail": "valid", "login": "x",
                                         "expires_at": None,
                                         "seconds_left": 10 ** 6})
    monkeypatch.setattr(R, "drive_token", lambda *a, **k: ("tok", "impersonating"))
    monkeypatch.setattr(R, "drive_identity", lambda: "dmai-worker@example")
    monkeypatch.setattr(R, "drive_get",
                        lambda path, **kw: ({"id": "f", "name": "General DMAs"}
                                            if path.startswith("files/")
                                            else {"files": [{"id": "c"}]}))
    monkeypatch.delenv("SECRETS_DOC_OPTIONAL", raising=False)


def _doc(monkeypatch, keys, status_ok=True, reason=""):
    # `raising=False` on the two functions the repair ADDED, so these tests run
    # against the pre-repair module too and fail on its BEHAVIOUR rather than
    # dying in the fixture with AttributeError. A negative control that cannot
    # execute the code it indicts proves only that the API changed — which is
    # the same "the check never ran" shape the repair itself is about.
    monkeypatch.setattr(R, "doc_secrets", lambda: dict(keys))
    monkeypatch.setattr(
        R, "doc_status",
        lambda: {"ok": status_ok, "keys": len(keys), "reason": reason},
        raising=False)


def test_a_404_on_the_doc_fails_the_preflight(monkeypatch, capsys):
    """THE defect. Pre-fix this returned 0 and the shell printed PASS."""
    _doc(monkeypatch, {}, status_ok=False,
         reason="404 — not shared with dmai-worker@example")
    assert R.main() == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "source of record" in out


def test_a_doc_that_parses_to_zero_keys_is_never_reported_ok(monkeypatch, capsys):
    """A fetch that yields no credentials is not a successful read."""
    _doc(monkeypatch, {}, status_ok=False, reason="parsed to 0 keys")
    assert R.main() == 1
    out = capsys.readouterr().out
    assert "parsed to 0 keys" in out
    # The old code printed `secrets doc OK 0 key(s) loaded` here.
    assert "OK    0 key(s)" not in out


def test_the_real_parser_reports_zero_keys_rather_than_success():
    """Same claim, one layer down: the branch is in `doc_secrets`, not only in
    the caller, so a caller that forgets to grade still cannot see an OK."""
    assert R._parse_doc("this doc has no recognisable credential notation") == {}


def test_a_reachable_doc_carrying_the_keys_passes(monkeypatch, capsys):
    _doc(monkeypatch, DOC_KEYS)
    monkeypatch.setattr(R, "credential_provenance", raising=False, value=
                        lambda: {k: "secrets doc" for k in DOC_KEYS})
    assert R.main() == 0
    assert "from the secrets doc" in capsys.readouterr().out


def test_a_credential_taken_from_secret_manager_says_so_and_degrades(
        monkeypatch, capsys):
    """The quiet failure the provenance line exists for: the doc is readable,
    but does not define this key, so a rotation there never reaches the run."""
    _doc(monkeypatch, {"DMA_ROUTINE_DRIVE_SA_KEY": DOC_KEYS[
        "DMA_ROUTINE_DRIVE_SA_KEY"]})
    monkeypatch.setattr(R, "credential_provenance", raising=False, value=
                        lambda: {"DMA_ROUTINE_GITHUB_PAT": "Secret Manager",
                                 "DMA_ROUTINE_DRIVE_SA_KEY": "secrets doc"})
    assert R.main() == 2                     # degraded, not clean, not fatal
    out = capsys.readouterr().out
    assert "from Secret Manager" in out
    assert "rotation" in out


def test_an_unresolvable_credential_fails(monkeypatch):
    _doc(monkeypatch, {})
    monkeypatch.setattr(R, "credential_provenance", raising=False, value=
                        lambda: {"DMA_ROUTINE_GITHUB_PAT": "UNRESOLVED (RuntimeError)"})
    assert R.main() == 1


def test_the_escape_hatch_must_be_chosen_and_still_is_not_silent(
        monkeypatch, capsys):
    """SECRETS_DOC_OPTIONAL=1 rides out a Docs outage — as WARN, never OK."""
    _doc(monkeypatch, DOC_KEYS, status_ok=False, reason="HTTP 503")
    monkeypatch.setattr(R, "credential_provenance", raising=False, value=
                        lambda: {k: "secrets doc" for k in DOC_KEYS})
    monkeypatch.setenv("SECRETS_DOC_OPTIONAL", "1")
    assert R.main() == 2
    out = capsys.readouterr().out
    assert "WARN" in out
    assert "source of record" in out


def test_absent_escape_hatch_does_not_leak_from_the_environment(monkeypatch):
    """Any value other than exactly "1" is not an opt-out. A stray empty
    string or "0" inherited from a shell must not disable the check."""
    _doc(monkeypatch, {}, status_ok=False, reason="HTTP 503")
    for val in ("", "0", "false", "no", "true"):
        monkeypatch.setenv("SECRETS_DOC_OPTIONAL", val)
        monkeypatch.setattr(R, "_DOC_STATUS", None, raising=False)
        assert R.main() == 1, f"SECRETS_DOC_OPTIONAL={val!r} disabled the check"


def test_no_verdict_line_ever_carries_a_credential(monkeypatch, capsys):
    """Every path above prints; none may print a value or a prefix of one."""
    for status_ok, reason in ((True, ""), (False, "404 — not shared"),
                              (False, "parsed to 0 keys")):
        monkeypatch.setattr(R, "_DOC_STATUS", None, raising=False)
        _doc(monkeypatch, DOC_KEYS, status_ok=status_ok, reason=reason)
        monkeypatch.setattr(R, "credential_provenance", raising=False, value=
                            lambda: {k: "secrets doc" for k in DOC_KEYS})
        monkeypatch.setenv("SECRETS_DOC_OPTIONAL", "1")
        R.main()
        out = capsys.readouterr().out
        for value in DOC_KEYS.values():
            assert value not in out
            assert value[:12] not in out
