"""A link whose two halves both work and are not joined.

WHY THESE EXIST. That sentence is the shape of this product's most expensive
defects, and every one of them had passing tests on both halves:

  · `classification.py` classified the Client Research Profile, the scanner
    wrote the kind, `_classify_artefact` dropped it (AUD-0169/0171);
  · `open_folder` recorded the client folder, `package` recomputed it, and a
    run could end with two of them (AUD-0183);
  · Entity_Timeline had a writer, a gate and no reader (AUD-0165);
  · the three scored tabs had a reader, two live gates and no writer
    (AUD-0166/0173).

`audit_chain.py` asserts each link of the pipeline has an OWNER, a GATE and a
READER. These tests pin the thing that makes that useful: that it FAILS when
a role goes missing. A completeness checker nobody has seen fail is a
completeness checker nobody should believe.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = HERE / "audit_chain.py"
sys.path.insert(0, str(HERE))
import audit_chain as A                                      # noqa: E402


def test_the_real_chain_has_no_hole():
    out = A.audit()
    assert not out["holes"], json.dumps(out["holes"], indent=1)


def test_every_link_declares_all_three_roles():
    out = A.audit()
    for row in out["links"]:
        for role in A.ROLES:
            assert row[role]["what"].strip(), (row["link"], role)


def test_it_covers_the_whole_chain_the_owner_named():
    """intake → deep research → enrichment cadence → workbook population →
    report finalization → web-app promotion → vetting. A chain audit that
    quietly stops at the package would report green on the half that has
    never been the problem."""
    links = " | ".join(r["link"] for r in A.audit()["links"]).lower()
    for stage in ("intake", "deep research", "enrichment", "workbook",
                  "report finalization", "package", "vetting", "synthesis",
                  "promotion", "served web app"):
        assert stage in links, f"no link covers {stage!r}"


def test_a_missing_role_is_reported_as_a_hole(monkeypatch):
    """The check that makes the rest of them mean something."""
    broken = list(A.LINKS)
    link, owner, gate, reader = broken[0]
    broken[0] = (link, ("a thing that is not there", lambda: False), gate,
                 reader)
    monkeypatch.setattr(A, "LINKS", broken)
    out = A.audit()
    assert out["holes"] and out["holes"][0]["missing"] == ["owner"], out


def test_a_check_that_raises_is_a_hole_not_a_pass(monkeypatch):
    """An exception inside a predicate must not read as satisfied — that is
    the same failure mode as an ERROR reading as a pass, which is what let 22
    schema tests sit unrun (AUD-0181)."""
    def boom():
        raise RuntimeError("no")

    broken = list(A.LINKS)
    link, owner, gate, reader = broken[0]
    broken[0] = (link, ("explodes", boom), gate, reader)
    monkeypatch.setattr(A, "LINKS", broken)
    out = A.audit()
    assert out["holes"][0]["missing"] == ["owner"]
    assert "RuntimeError" in out["holes"][0]["what"][0]


def test_strict_exits_nonzero_only_on_a_hole(monkeypatch):
    assert A.main(["--strict"]) == 0
    broken = list(A.LINKS)
    link, owner, gate, reader = broken[0]
    broken[0] = (link, ("absent", lambda: False), gate, reader)
    monkeypatch.setattr(A, "LINKS", broken)
    assert A.main(["--strict"]) == 1
    assert A.main([]) == 0, "without --strict it reports and exits 0"


def test_the_predicates_read_the_repository_rather_than_a_list():
    """If someone replaces a check with `lambda: True`, the audit becomes a
    list of claims. Pinned by requiring every predicate to touch the
    filesystem, a subprocess or the routine declarations."""
    src = SCRIPT.read_text()
    assert "lambda: True" not in src, "a hardcoded True is not a check"
    for helper in ("_exists", "_agent", "_grep", "_cmd", "_routine",
                   "_claude_routine"):
        assert f"def {helper}" in src and src.count(helper) > 2, helper


def test_the_script_answers_help():
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
