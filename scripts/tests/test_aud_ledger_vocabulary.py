"""A ledger its own tool cannot read is not a record.

WHY THESE EXIST. Fourteen findings were filed with severity `BLOCKING`
against a `SEV_ORDER` that knows only `BLOCKER`. Every mode of
`scripts/aud_ledger.py` — the summary, `--open`, `--verify`, `--md` — died on
a `KeyError: 'BLOCKING'`, and `.qa/AUD-DISPOSITIONS.md` went stale behind it,
because nothing runs the ledger on a schedule and a traceback out of a
reporting tool reads as a tool problem rather than a data one. Two more
drifts were hiding underneath: a disposition the tool did not know, and three
check NAMES cited by findings with no command anywhere in the `checks` map —
so `--verify` would have reported those rows as proved while running nothing
for them.

That last one is the reason this file is not merely a schema test. The whole
premise of the ledger is that a disposition names a RUNNABLE check, so a
citation with no command is the ledger quietly becoming the kind of artefact
it exists to refuse.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "aud_ledger.py"
LEDGER = ROOT / ".qa" / "AUD-DISPOSITIONS.json"
sys.path.insert(0, str(ROOT / "scripts"))
import aud_ledger as A                                       # noqa: E402


@pytest.fixture(scope="module")
def doc():
    return json.loads(LEDGER.read_text())


def test_every_severity_is_one_the_tool_orders(doc):
    bad = sorted({r["sev"] for r in doc["findings"]
                  if r["sev"] not in A.SEV_ORDER})
    assert not bad, f"{bad} would raise KeyError in every mode of the tool"


def test_every_disposition_is_one_the_tool_counts(doc):
    bad = sorted({r["disposition"] for r in doc["findings"]
                  if r["disposition"] not in A.DISPOSITIONS})
    assert not bad, f"{bad} is counted nowhere and prints in no column"


def test_every_check_a_finding_cites_has_a_command(doc):
    """`--verify` runs the command a name maps to. A name with no command is
    a disposition that proves nothing while reading as proved."""
    missing = sorted({c for r in doc["findings"]
                      for c in r.get("checks", ())
                      if c not in doc["checks"]})
    assert not missing, f"cited with no command: {missing}"


def test_every_command_in_the_map_is_actually_cited(doc):
    """The other direction is not a defect but it is a smell: a check nobody
    cites is a proof nobody claimed. Reported, not enforced — a command may
    legitimately be added a moment before the finding that uses it."""
    cited = {c for r in doc["findings"] for c in r.get("checks", ())}
    orphans = sorted(set(doc["checks"]) - cited)
    assert len(orphans) <= 4, f"{orphans} — commands no finding rests on"


def test_load_refuses_a_ledger_it_cannot_read(tmp_path, monkeypatch):
    bad = {"_why": [], "checks": {},
           "findings": [{"id": "X-1", "sev": "BLOCKING", "area": "a",
                         "title": "t", "target": "t",
                         "disposition": "FIXED", "checks": []}]}
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(bad))
    monkeypatch.setattr(A, "LEDGER", path)
    with pytest.raises(SystemExit) as e:
        A.load()
    assert "BLOCKING" in str(e.value) and "X-1" in str(e.value), e.value


def test_load_names_a_cited_check_that_has_no_command(tmp_path, monkeypatch):
    bad = {"_why": [], "checks": {},
           "findings": [{"id": "X-2", "sev": "MAJOR", "area": "a",
                         "title": "t", "target": "t",
                         "disposition": "OPEN", "checks": ["nowhere"]}]}
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(bad))
    monkeypatch.setattr(A, "LEDGER", path)
    with pytest.raises(SystemExit) as e:
        A.load()
    assert "nowhere" in str(e.value), e.value


# ── every mode must actually run against the real ledger ─────────────────

@pytest.mark.parametrize("args", [[], ["--open"], ["--md"]])
def test_the_tool_runs_over_the_real_ledger(args):
    r = subprocess.run([sys.executable, str(SCRIPT)] + args,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip(), f"{args} printed nothing"


def test_the_generated_markdown_is_current():
    """`.qa/AUD-DISPOSITIONS.md` is generated. It sat stale behind the
    KeyError for as long as the drift lasted, so the file being current is
    itself the check that the tool ran."""
    r = subprocess.run([sys.executable, str(SCRIPT), "--md"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    on_disk = (ROOT / ".qa" / "AUD-DISPOSITIONS.md").read_text()
    assert on_disk.strip() == r.stdout.strip(), \
        "regenerate with: python3 scripts/aud_ledger.py --md > " \
        ".qa/AUD-DISPOSITIONS.md"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
