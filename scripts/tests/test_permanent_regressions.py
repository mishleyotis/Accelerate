"""The permanent regression corpus holds, and holds in the only direction allowed.

`fixtures/permanent_regressions.json` registers every finding a person this
product answers to has flagged — thirteen at commit — each with the pin that
keeps it from recurring. This meta-test is what makes the register load-bearing
rather than a list somebody wrote once:

  * no entry is retirable, ever;
  * every `test` pin names a file that exists AND a test id pytest actually
    collects — a pin pointing at a renamed or deleted test is a pin pointing
    at nothing, and it fails here the day the rename lands, not the day the
    regression ships;
  * every `gate` pin's id is registered in the connector's GATES dict, so a
    registry renumber that orphans a pinned id is caught the same way;
  * every `OPEN` pin is printed as a work-report line — OPEN is allowed
    (recording no pin honestly beats inventing one) but it is counted, and the
    count may only shrink.

The corpus may grow (a newly flagged finding belongs here the run it is
flagged) and OPEN pins may be flipped to real tests or gates. Entries are
never removed and pins are never weakened; the rectifier skill's
"The permanent corpus" section states the same rules from the write side.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "fixtures" / "permanent_regressions.json"

# The number of OPEN pins committed with the corpus (MEM-0017 prompt-shape
# regression case, MEM-0057 known-bad reference run, MEM-0062 Explorium ingest
# job, MEM-0065 IAP page fetch, MEM-0068 peer-basis render check). DECREASING
# this constant — by flipping an OPEN pin to a real test or gate and lowering
# it in the same commit — is the only allowed direction. Raising it means a
# user-flagged finding shipped without a pin, which is the thing this corpus
# exists to make visible: add the entry, count its OPEN pin here, and treat
# the raise as the work order it is.
OPEN_PINS_COMMITTED = 5

# The thirteen findings flagged at commit. The corpus may grow past them;
# it may never lose one of them.
FOUNDING_FINDINGS = {
    "MEM-0013", "MEM-0014", "MEM-0017", "MEM-0057", "MEM-0058", "MEM-0059",
    "MEM-0060", "MEM-0062", "MEM-0063", "MEM-0064", "MEM-0065", "MEM-0068",
    "MEM-0095",
}

PIN_KINDS = {"test", "gate", "OPEN"}


def _entries():
    return json.loads(CORPUS.read_text())["entries"]


def _pins(kind):
    return [(e["finding_id"], p["ref"])
            for e in _entries() for p in e["pinned_by"] if p["kind"] == kind]


def test_the_corpus_loads_and_no_founding_finding_is_missing():
    ids = [e["finding_id"] for e in _entries()]
    assert len(ids) == len(set(ids)), "duplicate finding_id in the corpus"
    missing = FOUNDING_FINDINGS - set(ids)
    assert not missing, (
        f"founding findings removed from the corpus: {sorted(missing)} — "
        "entries are added, never removed")


def test_every_entry_has_the_full_shape_and_is_not_retirable():
    for e in _entries():
        for key in ("finding_id", "title", "flagged_by",
                    "what_must_never_recur", "pinned_by", "retirable"):
            assert key in e, f"{e.get('finding_id', '?')} missing {key}"
        assert e["retirable"] is False, (
            f"{e['finding_id']} marked retirable — no entry in this corpus "
            "ever is")
        assert e["pinned_by"], f"{e['finding_id']} has no pins at all — " \
            "an unpinned regression is recorded as an OPEN pin, not as nothing"
        for p in e["pinned_by"]:
            assert p.get("kind") in PIN_KINDS, (
                f"{e['finding_id']} pin kind {p.get('kind')!r} is not one of "
                f"{sorted(PIN_KINDS)}")
            assert isinstance(p.get("ref"), str) and p["ref"].strip(), (
                f"{e['finding_id']} carries a pin with no ref")


def test_every_test_pin_names_a_file_that_exists():
    for fid, ref in _pins("test"):
        path = ref.split("::", 1)[0]
        assert "::" in ref, (
            f"{fid}: test pin {ref!r} names no test id — a bare file is not "
            "a pin, because deleting one test inside it would go unnoticed")
        assert (ROOT / path).is_file(), (
            f"{fid}: test pin file {path} does not exist")


def test_every_test_pin_is_collected_by_pytest():
    """One subprocess for all pins: pytest --collect-only exits non-zero if
    any named id does not resolve, and each collected id echoes to stdout."""
    refs = sorted({ref for _, ref in _pins("test")})
    assert refs, "the corpus pins no tests at all, which cannot be right"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-p", "no:cacheprovider", *refs],
        cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, (
        "pytest could not collect every pinned test id:\n"
        f"{proc.stdout}\n{proc.stderr}")
    for ref in refs:
        assert ref in proc.stdout, (
            f"pinned test id not in the collection report: {ref}")


def test_every_gate_pin_is_registered_in_the_connector():
    sys.path.insert(0, str(ROOT / "apps" / "mcp"))
    try:
        from dma_mcp.gates import GATES
    finally:
        sys.path.pop(0)
    for fid, ref in _pins("gate"):
        assert ref in GATES, (
            f"{fid}: gate pin {ref} is not in the connector's registry — if "
            "the registry renumbered, the entry follows the check to its new "
            "id; it does not lose its pin")


def test_open_pins_are_reported_and_the_count_only_shrinks():
    """OPEN pins are honest debt: allowed, printed, counted. The committed
    constant moves DOWN when an OPEN pin becomes a real test or gate, and in
    no other direction."""
    open_pins = _pins("OPEN")
    for fid, ref in open_pins:
        print(f"OPEN PIN — {fid}: the missing check must assert: {ref}")
        assert len(ref) >= 40, (
            f"{fid}: an OPEN ref must say what the missing test will assert, "
            "in enough words to write it from — this one does not")
    assert len(open_pins) <= OPEN_PINS_COMMITTED, (
        f"{len(open_pins)} OPEN pins against a committed ceiling of "
        f"{OPEN_PINS_COMMITTED}. A new user-flagged finding without a pin "
        "raises the constant in the same commit, on purpose and visibly; "
        "nothing else does.")
