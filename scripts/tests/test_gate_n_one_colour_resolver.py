"""Gate N's negative control: it must be able to fail.

AUD-0050 measured the acceptance ledger claiming CI enforced invariant 7
while BD-04 sat in gate E's textless list with no rule and no test. A gate
with only a happy-path test is the same claim in a different file."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "gate_n_one_colour_resolver.py"
GEN = ROOT / "scripts" / "gen_proto_bands.py"
LIB = ROOT / "apps" / "web" / "lib" / "bands.js"
PROTO = ROOT / "apps" / "web" / "proto" / "bands.js"
DATA = ROOT / "apps" / "web" / "proto" / "data.js"


def _run(script, *args):
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, timeout=120)


def test_the_repository_holds_one_resolver_today():
    r = _run(GATE)
    assert r.returncode == 0, r.stdout


def test_the_generated_resolver_is_current():
    r = _run(GEN, "--check")
    assert r.returncode == 0, r.stdout


def test_a_hand_edit_to_the_generated_file_is_caught(tmp_path):
    original = PROTO.read_text()
    try:
        PROTO.write_text(original.replace("#139F94", "#185F60"))
        assert _run(GEN, "--check").returncode == 1
        assert _run(GATE).returncode == 1
    finally:
        PROTO.write_text(original)
    assert _run(GATE).returncode == 0


def test_a_second_colour_mapping_anywhere_fails_the_gate():
    """The AUD-0048 shape: a call site that maps a score to a hex itself."""
    probe = ROOT / "apps" / "web" / "proto" / "_gate_n_probe.jsx"
    probe.write_text(
        "function hexFor(s) {\n"
        "  if (s == null) return \"#E5E7EB\";\n"
        "  return s < 2 ? \"#FFCB99\" : \"#139F94\";\n"
        "}\n")
    try:
        r = _run(GATE)
        assert r.returncode == 1
        assert "_gate_n_probe.jsx" in r.stdout
    finally:
        probe.unlink()
    assert _run(GATE).returncode == 0


def test_a_comment_explaining_the_rule_is_not_a_violation():
    """The gate strips comments before scanning. Without that it flags the
    paragraph in data.js that documents why #E5E7EB is forbidden — and the
    cheapest way to pass would be to delete the explanation."""
    assert "#E5E7EB" in DATA.read_text()
    assert _run(GATE).returncode == 0


# ── the behaviour the second resolver got wrong ──────────────────────────

def test_a_null_score_resolves_to_no_colour_at_all():
    """AUD-0049: maturityHex(null) returned #E5E7EB — a grey swatch for a
    measurement that was never taken (invariants 6 and 9)."""
    out = subprocess.run(
        ["node", "-e",
         f"global.window={{}};require({str(PROTO)!r});"
         "const B=global.window.DMA_BANDS;"
         "console.log(JSON.stringify([B.hexFor(null),B.hexFor(undefined),"
         "B.labelFor(null),B.classFor(null),B.hexFor('nonsense')]));"],
        capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    hexes = json.loads(out.stdout)
    assert hexes[:4] == [None, None, None, "muted"]
    assert hexes[4] is None


@pytest.mark.parametrize("score,band", [
    (1.9999, "Activating"), (2.0, "Building"), (2.9999, "Building"),
    (3.0, "Competing"), (3.9999, "Competing"), (4.0, "Differentiating"),
    (5.0, "Differentiating"),
])
def test_four_branches_strict_less_than_on_the_raw_score(score, band):
    out = subprocess.run(
        ["node", "-e",
         f"global.window={{}};require({str(PROTO)!r});"
         f"console.log(global.window.DMA_BANDS.labelFor({score}));"],
        capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == band


def _code(text: str) -> str:
    """Comments blanked. Both resolvers NAME the forbidden hex in order to
    forbid it, and a test that cannot tell a rule from a violation makes
    deleting the rule the cheapest way to pass."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"^\s*//.*$", " ", text, flags=re.M)


def test_there_is_no_fifth_band_and_no_hex_for_one():
    code = _code(PROTO.read_text()) + _code(LIB.read_text())
    assert "185F60" not in code
    assert "Transformational" not in code
    assert len(re.findall(r'return "(?:Activating|Building|Competing|'
                          r'Differentiating)"', _code(PROTO.read_text()))) == 4


# ── AUD-0050 · the ledger no longer claims what nothing does ─────────────

def test_bd04_has_rule_text_and_names_its_enforcer():
    inv = json.loads((ROOT / "apps/web/tests/acceptance/inventory.json")
                     .read_text())
    rows = [c for s in inv["sections"] for c in (s.get("checks") or [])
            if c.get("qa_id") == "BD-04"]
    assert rows, "BD-04 is not in the inventory at all"
    for r in rows:
        assert len(str(r.get("rule") or "")) > 20
        assert r.get("enforced_by") == "scripts/gate_n_one_colour_resolver.py"


def test_bd04_is_out_of_the_textless_backlog():
    d = json.loads((ROOT / "apps/web/tests/acceptance/gate_e_ratchet.json")
                   .read_text())
    assert "register.bd:BD-04" not in d["textless_adopts"]
