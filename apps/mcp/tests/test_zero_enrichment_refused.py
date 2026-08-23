"""A run with nothing enriched is an empty shell, and it used to promote.

Owner, 2026-08-23, reporting eight separate defects on promoted runs: a
platform readiness card with no depth, sentiment carrying one parameter, an
evolution timeline spanning one year, too few techstack items, platform cards
reading "0 recs", Clay enrichment with no emails, under three historical news
items, and empty cards throughout.

Measured against every promoted client the same day (MEM-0206):

    gulf-coast-business-credit   7 of 7 facets never_enriched   (70 cells)
    axos-bank-…-nyse-ax          7 of 7 never_enriched          (355 cells)
    baxter-credit-union-bcu      7 of 7 never_enriched          (765 cells)
    logix-federal-credit-union   0 of 7 — every facet current   (705 cells)

Three of four promoted clients had never had a single enrichment facet run,
and every one of them promoted. All eight reported defects reduce to that.

"The routine never runs in degrade mode" (owner, 2026-08-20) was written into
a Routine prompt, and prose is not evaluated — the same lesson as the version
floors. promote_run already READ the facet states, a hundred lines below the
writers, to report them. What was missing was a consequence.

THE LINE IS AT ZERO, and the distinction is the whole design. The existing
disclosure argues correctly that a promote carrying five of seven facets
forward beats no promote, because refusing would strand the five. That
argument has a floor it never drew: at zero there is nothing to strand.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dma_mcp import ledger  # noqa: E402


ALL_FACETS = ("firmographics", "leadership", "peer_scores",
              "platform_readiness", "sentiment", "techstack", "why_now")


def rows(**states):
    """Facet rows as ledger.drift returns them, defaulting to never_enriched."""
    return [{"facet": f, "state": states.get(f, "never_enriched"),
             "enrichment_version": None, "enriched_at": None,
             "promoted_version": 0, "promoted_at": None}
            for f in ALL_FACETS]


def refuses(facet_rows) -> bool:
    """The gate's predicate, as promote_run applies it."""
    return bool(facet_rows) and all(
        r["state"] == "never_enriched" for r in facet_rows)


# ── the case that shipped ─────────────────────────────────────────────────

def test_zero_of_seven_is_refused():
    """Gulf Coast, Axos and Baxter, exactly as measured."""
    assert refuses(rows()) is True


@pytest.mark.parametrize("facet", ALL_FACETS)
def test_one_enriched_facet_is_enough_to_promote(facet):
    """PARTIAL MUST STILL PROMOTE. Refusing here would strand the facet that
    did run, and the whole point of the floor is that it sits at zero."""
    assert refuses(rows(**{facet: "current"})) is False


def test_enriched_but_not_yet_promoted_also_counts_as_run():
    """`enriched_not_promoted` means the work HAPPENED and is waiting to be
    carried forward — which is what this promote is for. Treating it as
    never_enriched would refuse the very transaction that fixes it."""
    assert refuses(rows(sentiment="enriched_not_promoted")) is False


def test_the_reference_client_is_unaffected():
    """Logix: every facet current. A gate that touched it would be wrong."""
    assert refuses(rows(**{f: "current" for f in ALL_FACETS})) is False


# ── the blind spot, which must be named rather than passed ────────────────

def test_no_facet_rows_does_not_refuse():
    """The ledger knowing nothing about an entity is not the same fact as
    seven facets saying never_enriched, and the gate must not invent the
    stronger claim from the weaker evidence."""
    assert refuses([]) is False


def test_but_the_unknown_is_disclosed():
    """…and it must not pass as "fine" either. The success path says so."""
    src = (Path(__file__).resolve().parents[1] / "dma_mcp" / "promote.py").read_text()
    assert '"facets_unknown"' in src
    assert "UNKNOWN rather than" in src


# ── the refusal has to be actionable ──────────────────────────────────────

def test_the_refusal_names_the_way_out():
    src = (Path(__file__).resolve().parents[1] / "dma_mcp" / "promote.py").read_text()
    assert '"no_enrichment_ever_run"' in src
    assert "record_enrichment" in src, "the caller is told which tool clears it"
    assert "came\n                    f\"back EMPTY" in src or "back EMPTY" in src, (
        "an EMPTY enrichment result is a real result and must clear the gate — "
        "otherwise a client with genuinely nothing to find can never promote")
    assert "PARTIAL result does not reach this" in src, (
        "the caller is told the floor is zero, not seven")


def test_the_refusal_rolls_back():
    """It sits BEFORE the section writers, so a refused promote writes no
    serving rows — invariant 3 is all-or-nothing and this is the nothing."""
    src = (Path(__file__).resolve().parents[1] / "dma_mcp" / "promote.py").read_text()
    gate = src.index("no_enrichment_ever_run")
    writers = src.index('stats = {p: {"sections": 0, "rows_written": 0}')
    assert gate < writers, "the gate must refuse before anything is written"
    assert "conn.rollback()" in src[max(0, gate - 400):gate]


# ── the ledger's own vocabulary, so the gate cannot drift from it ─────────

def test_the_states_are_the_ledgers_states():
    assert set(ledger.STATES) == {"current", "enriched_not_promoted",
                                  "never_enriched"}
    assert "never_enriched" in ledger.BLOCKING_STATES


def test_every_facet_the_ledger_knows_is_covered_here():
    """If a facet is added, this test fails until the fixture knows it —
    which is the point: a new facet nobody watches is how the count drifts."""
    assert set(ledger.FACETS) == set(ALL_FACETS), (
        f"ledger facets {sorted(ledger.FACETS)} vs fixture {sorted(ALL_FACETS)}")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
