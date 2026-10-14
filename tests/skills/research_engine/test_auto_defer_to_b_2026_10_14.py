"""A version-A page that cites post-checkpoint evidence moves to B by itself.

R-INTERAC (2026-10-12) needed the owner's `--defer-to-b`; AAA WCNY
(2026-10-14) halted PAGES_A the same way: techstack cited E-249..E-252,
registered while REPORTS serviced an evidence upstream item — after INGEST_A —
so "does not resolve" on version A whatever the page did.
"""
from engine import pipeline as P
from engine import pipeline_stub as S
from fixtures import researched_run


def _pipe(run, tmp_path):
    opts = P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False, folder_root=tmp_path / "o",
                     ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None)
    return P.Pipeline(run, opts)


def test_a_page_citing_locally_registered_ids_is_deferred(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    local = next(iter(run.open().evidence_index()))
    pl = _pipe(run, tmp_path)
    verdicts = {"techstack": [{"gate_id": "ET-01", "message":
                               f"{local} does not resolve — fabricated or not yet registered"}]}
    left = pl._auto_defer_to_b({"techstack": "did not converge"}, verdicts, "A")
    assert left == {}
    assert pl._deferred() == ("techstack",)
    ok, why = pl.done("PAGES_A")
    assert "techstack" not in why.split("pending:")[-1]
    assert any(r.get("Gate") == "PAGES_DEFERRED_TO_B" and "automatically" in str(r.get("Detail"))
               for r in run.open().rows("Gate_Log"))


def test_a_truly_unknown_id_still_halts(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    pl = _pipe(run, tmp_path)
    verdicts = {"techstack": [{"gate_id": "ET-01", "message": "E-9999 does not resolve"}]}
    assert pl._auto_defer_to_b({"techstack": "x"}, verdicts, "A") == {"techstack": "x"}
    assert pl._deferred() == ()


def test_version_b_never_defers(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    local = next(iter(run.open().evidence_index()))
    pl = _pipe(run, tmp_path)
    verdicts = {"techstack": [{"gate_id": "ET-01", "message": f"{local} does not resolve"}]}
    assert pl._auto_defer_to_b({"techstack": "x"}, verdicts, "B") == {"techstack": "x"}
