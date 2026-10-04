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
