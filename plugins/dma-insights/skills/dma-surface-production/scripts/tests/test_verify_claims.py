"""verify_claims.py over a drafts file: the producer-side check that a
drawer's sentences are in their own excerpts (QA audit F-D04-005)."""
import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verify_claims", SCRIPTS / "verify_claims.py")
vc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vc)

E1 = ("Alkami digital banking went live in Q3 2024 and reached 47 percent member "
      "adoption within ninety days, restated at 50 percent in the 2025 report.")


def _drafts(tmp_path, cells):
    p = tmp_path / "drafts.json"
    p.write_text(json.dumps({"cell_evidence": {"data": {"cells": cells}}}))
    return p


def test_a_drawer_quoting_what_its_excerpt_does_not_say_fails(tmp_path, capsys):
    cells = [
        {"subcap_id": "P1C1.1.1", "thin": False,
         "synthesis": "Alkami digital banking went live in Q3 2024 [E-1].",
         "items": [{"e_id": "E-1", "excerpt": E1}]},
        {"subcap_id": "P1C1.1.2", "thin": False,
         "synthesis": "CEO Jason Mullins said onboarding fell from hours to minutes.",
         "items": [{"e_id": "E-1", "excerpt": E1}]},
    ]
    assert vc.main([str(_drafts(tmp_path, cells)), "--entity", "Acme Credit Union"]) == 1
    out = capsys.readouterr().out
    assert "NOT_SUPPORTED P1C1.1.2" in out and "entailed 1" in out


def test_a_clean_array_passes_and_a_declared_absence_is_spared(tmp_path):
    cells = [
        {"subcap_id": "P1C1.1.1", "thin": False,
         "synthesis": "Member adoption reached 47 percent within ninety days.",
         "items": [{"e_id": "E-1", "excerpt": E1}]},
        {"subcap_id": "P1C4.1.6", "thin": True, "items": [],
         "synthesis": "Test plans and sign-off records: none visible in the public record.",
         "sources_searched": ['searched for: "sign-off record" — 0 hits'],
         "closure_condition": "A sign-off record from the rollout."},
    ]
    assert vc.main([str(_drafts(tmp_path, cells))]) == 0
    out = vc.verify(json.loads(_drafts(tmp_path, cells).read_text()))
    assert out["counts"]["entailed"] == 1 and out["counts"]["frame"] == 1


def test_it_accepts_a_bare_cells_list_and_strict_refuses_partial(tmp_path):
    cells = [{"subcap_id": "P1C1.1.1", "thin": False,
              "synthesis": "Digital banking adoption grew quickly after launch.",
              "items": [{"e_id": "E-1", "excerpt": E1}]}]
    p = tmp_path / "cells.json"
    p.write_text(json.dumps(cells))
    assert vc.main([str(p)]) == 0
    assert vc.main([str(p), "--strict"]) == 1
