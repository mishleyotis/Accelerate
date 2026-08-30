"""The rule lives in two files, so a test holds them together.

`apps/api/dma_api/subverticals.py` decides which cells a run may SERVE;
`apps/mcp/dma_mcp/subverticals.py` decides which cells a payload may CITE
(ET-05). They are the same rule, and the two services cannot import one
module — each image copies only its own package.

They had already drifted. Measured 2026-08-15: the two `resolve_subvertical`
bodies differed, which means a cell the connector admitted at submit could be
one the API hid at serve, or the reverse. A gate and a filter disagreeing about
who the client is, silently, in opposite directions.

So the shared core — the alias table through `serves()` — must be byte-identical
in both. What sits BELOW `serves()` is each service's own: the API adds
`SCOPE_TAG` and `scope_to_entity`, the connector adds `SUBVERTICAL_NAMES` for
verdict prose. Those do not sync and this test does not ask them to.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps" / "api" / "dma_api" / "subverticals.py"
MCP = ROOT / "apps" / "mcp" / "dma_mcp" / "subverticals.py"

START = "_SUBVERTICAL_ALIASES = {"
# An explicit sentinel in BOTH files, not "the next definition" — inferring
# the end from whatever happens to follow is how a comparison quietly starts
# comparing the wrong range, and a guard that measures the wrong thing passes
# for the wrong reason.
END = "# ── END SHARED CORE"
DROP = ("def scope_status(", "def variant_subvertical(")   # API-only reporter


def _core(text: str) -> str:
    assert START in text and END in text, "core markers missing"
    body = text[text.index(START):text.index(END)]
    # `scope_status` is the API's own reporter and sits inside the range.
    if DROP[0] in body:
        body = body[:body.index(DROP[0])] + body[body.index(DROP[1]):]
    return body.rstrip() + "\n"


def test_the_shared_core_is_byte_identical():
    a, b = _core(API.read_text()), _core(MCP.read_text())
    if a != b:
        import difflib
        diff = "\n".join(list(difflib.unified_diff(
            a.splitlines(), b.splitlines(), "api", "mcp", lineterm=""))[:40])
        raise AssertionError(
            "the sub-vertical core has drifted between the API and the "
            "connector. A cell one admits and the other hides is a silent "
            f"disagreement about who the client is.\n\n{diff}")


def test_the_core_actually_contains_the_rule():
    """A guard on the guard: if the markers stop matching, `_core` would
    compare two empty strings and pass forever."""
    core = _core(API.read_text())
    for needed in ("def resolve_subvertical(", "def serves(",
                   "def variant_subvertical(", "_SV_TOKEN", "SUBVERTICAL_CODES"
                   if "SUBVERTICAL_CODES" in core else "_ALIAS_INDEX"):
        assert needed in core, f"the extracted core is missing {needed}"
    assert len(core) > 1500, f"core is only {len(core)} chars — markers moved"


def test_both_modules_agree_on_every_corpus_spelling():
    """Not just identical source — identical ANSWERS, through real imports."""
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    sys.path.insert(0, str(ROOT / "apps" / "mcp"))
    from dma_api.subverticals import resolve_subvertical as api_r
    from dma_mcp.subverticals import resolve_subvertical as mcp_r
    from dma_api.subverticals import serves as api_s
    from dma_mcp.subverticals import serves as mcp_s

    for raw in ("SV2", "SV5 — RIAs & Broker-Dealers (Canada)", "Credit Unions",
                "SV1 — Regional Banks", "Insurance & Wealth (IC/AM)",
                "HIGH", "", None, "Regional Bank", "SV7_Insurance_Brokers"):
        assert api_r(raw) == mcp_r(raw), f"disagree on {raw!r}"
    for cell in ("P1C1.3.IC1", "P1C1.3.CU1", "P1C1.3.2", "P1C2.7.BK1",
                 "P3C4.2.PEN1", "P2C4.6.RIA1"):
        for code in ("CU", "RIA", "IC", None):
            assert api_s(cell, code) == mcp_s(cell, code), f"{cell}/{code}"
