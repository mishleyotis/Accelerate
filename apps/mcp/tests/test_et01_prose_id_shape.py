"""ET-01 (prose) — a word that looks like an id is not a citation.

MEM-0541 (GATE_FIRES_ON_VERBATIM_SPAN; 3 sightings on SWBC run 7968492e,
2026-09-16 to 2026-10-04). An r_layer probe quoted a registered T1
BrokerCheck excerpt verbatim — "NO SUPERVISOR, NO VALID CONTACT/E-MAIL" — and
ET-01's in-prose scanner matched `E-MAIL` against the evidence-id recogniser
(`E-` + any word characters), found it unresolvable and blocked. CG-27 forbids
rewriting a verbatim span; ET-01 blocked until it was rewritten. The producer
replaced E-CC-925 with a shorter span in 7 drawers to get past it.

The fix (the finding's option c, the narrowest): in PROSE, a token counts as a
citation only in the run's own evidence-id shapes — E-<digits>,
E-<TOKEN>-<digits>, E-CC-<digits>, an optional -R<n> revision, EV-<scope>-
<digits>, INT-<label> — so a token with no numeric segment (E-MAIL, E-SIGN,
E-COMMERCE) is a word. The keyed path is untouched: a value under `e_ids` is
still checked whatever it looks like.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import validation2  # noqa: E402


def _run(monkeypatch, text, found=()):
    def fake(conn, run_id, ids):
        return {"found": [{"e_id": e} for e in ids if e in found],
                "not_found": [e for e in ids if e not in found],
                "foreign": []}
    monkeypatch.setattr(validation2, "get_evidence", fake)
    payload = {"cards": {"cards": [{"r_layer": {"probes_run": [text]}}]}}
    return validation2._check_prose_citations_resolve(None, "run", payload, {})


def test_a_quoted_excerpt_containing_e_mail_is_not_a_citation(monkeypatch):
    out = _run(monkeypatch, 'E-CC-925 reads "NO SUPERVISOR, NO VALID '
                            'CONTACT/E-MAIL" verbatim.', found={"E-CC-925"})
    assert out == [], out


def test_other_e_words_are_words(monkeypatch):
    assert _run(monkeypatch, "E-SIGN and E-COMMERCE and E-BANKING rollout") \
        == []


def test_a_real_unresolvable_id_in_prose_still_blocks(monkeypatch):
    out = _run(monkeypatch, "as shown in [E-WLI-047-R2] and E-0471")
    assert {r["gate_id"] for r in out} == {"ET-01"}
    assert len(out) == 2


def test_an_invented_mint_id_in_prose_is_still_et02(monkeypatch):
    out = _run(monkeypatch, "per E-CC-99999")
    assert [r["gate_id"] for r in out] == ["ET-02"]


# ── fix2/gates (review of fix/mcp-gates-contract, 2026-10-04) ─────────────
#
# The first cut of the prose filter was NARROWER than the id shapes the
# system stores, so a real-looking id of those shapes was dropped before
# get_evidence was ever asked — an unresolvable or FOREIGN citation then
# passed silently, and `foreign` is supposed to halt production (invariant 4).
# The stored shapes come from apps/worker/dma_worker/evidence_ids.py
# (STORED_PACKAGE: E-{TOKEN}-nnn with -R{run_seq} and/or the cross-entity
# -{ENT6} escape, tokens that may start with a digit), the server mint
# E-CC-nnn (register.py), package-local ids as the workbook ships them (E-047,
# E-047:F1, letter-prefixed E-A047), connector EV-{scope}-nnn and INT-{label}.
# Every one of them must still be LOOKED UP when it appears in a sentence.
STORED_SHAPES = [
    "E-UNK-007-1FCA91",        # cross-entity escape, manifest-less package
    "E-UNK-192-53D062",        # the 14-entity UNK namespace
    "E-BCU-006-R2-1FCA91",     # run re-mint, then the cross-entity escape
    "E-BCU-006-R2",            # run re-mint
    "E-1STNB-012",             # a token that starts with a digit
    "E-NORTHERN-047",          # the readable qualified form
    "E-CC-1240",               # server mint, four digits
    "E-047",                   # package-local, as the workbook ships it
    "E-A047",                  # letter-prefixed workbook id (workbook_parser)
    "EV-INDEED-003",           # connector namespace
    "INT-MGMT-01",             # internal namespace
]


def _lookup_spy(monkeypatch, verdict="not_found", owner="another entity"):
    asked = []

    def fake(conn, run_id, ids):
        asked.extend(ids)
        if verdict == "foreign":
            return {"found": [], "not_found": [],
                    "foreign": [{"e_id": e, "belongs_to": owner}
                                for e in ids]}
        return {"found": [], "not_found": list(ids), "foreign": []}
    monkeypatch.setattr(validation2, "get_evidence", fake)
    return asked


def _prose(text):
    payload = {"cards": {"cards": [{"body_md": text}]}}
    return validation2._check_prose_citations_resolve(None, "run", payload, {})


def test_every_stored_id_shape_is_looked_up_and_refused_when_unresolvable(
        monkeypatch):
    for e in STORED_SHAPES:
        asked = _lookup_spy(monkeypatch)
        out = _prose(f"as the filing states (per {e}), the branch closed.")
        assert asked == [e], (e, asked)
        want = "ET-02" if e.startswith("E-CC-") else "ET-01"
        assert [r["gate_id"] for r in out] == [want], (e, out)


def test_a_fact_grain_package_citation_is_looked_up(monkeypatch):
    asked = _lookup_spy(monkeypatch)
    out = _prose("the roadmap names three phases [E-047:F1]")
    assert asked == ["E-047"] and len(out) == 1


def test_a_foreign_escape_id_in_prose_halts(monkeypatch):
    """The exact hole the review measured: 'per E-UNK-007-1FCA91' returned []
    without a lookup. A foreign row must surface as contamination."""
    _lookup_spy(monkeypatch, verdict="foreign", owner="Tri Counties Bank")
    out = _prose("per E-UNK-007-1FCA91 the institution reports 41 branches")
    assert len(out) == 1 and out[0]["gate_id"] == "ET-01"
    assert "STOP" in out[0]["message"]
    assert "Tri Counties Bank" in out[0]["message"]


def test_words_with_no_digit_are_still_words(monkeypatch):
    for word in ("E-MAIL", "E-SIGN", "E-COMMERCE", "E-BANKING",
                 "E-STATEMENTS", "E-NOTICES", "EV-CHARGING"):
        asked = _lookup_spy(monkeypatch)
        assert _prose(f'the excerpt reads "{word} enrolment" verbatim') == []
        assert asked == [], (word, asked)


def test_the_recogniser_finds_every_stored_shape_whole():
    from dma_mcp.identifiers import find_ids
    for e in STORED_SHAPES:
        assert find_ids(f"see {e}.") == [e], e
