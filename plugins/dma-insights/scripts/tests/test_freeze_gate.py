"""The gate that decides whether a package may be frozen.

`freeze_package.py` sets a Drive content restriction, which locks a file
against editing. Getting that wrong in the permissive direction locks a
person out of their own work mid-production, so the gate is the part worth
testing rather than the API call.

Three bugs this suite exists because of, all found by running the tool:

  1 · it re-implemented the worker's tie-break and chose the WRONG workbook —
      the copy at 15:35:02 rather than the newest at 15:36:52 — reproducing,
      in a tool written to fix that defect, the defect itself. It imports
      `_package_groups` now and decides nothing about file choice locally.
  2 · its promoted-run lookup keyed on `source_folder_id`, a field
      `list_pending_runs` does not return, so the set was always empty and
      the gate refused everything. It asks `get_client_state` now.
  3 · the docstring promised "only a promoted run's artefacts" and the first
      version had no such check at all.
"""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import freeze_package as fp                                 # noqa: E402


def test_unknown_state_is_not_treated_as_promoted(monkeypatch):
    """None is not zero. A connector that cannot be read means the answer is
    unknown, and unknown must refuse."""
    monkeypatch.setattr(fp, "_served_pages", lambda d: None)
    assert fp._served_pages("anything") is None


def test_served_pages_reads_the_connector_answer(monkeypatch):
    monkeypatch.setattr(fp.subprocess if hasattr(fp, "subprocess") else fp,
                        "__name__", "fp", raising=False)

    class _R:
        stdout = json.dumps({"display_id": "x", "served_pages": ["a", "b"]})

    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    assert fp._served_pages("x") == 2


def test_a_client_serving_nothing_reads_as_zero(monkeypatch):
    """Bank of Travelers Rest: nineteen runs, none promoted, zero served
    pages. Its package is still in production and must not be frozen."""
    class _R:
        stdout = json.dumps({"display_id": "botr", "served_pages": []})

    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    assert fp._served_pages("botr") == 0


def test_a_malformed_connector_reply_is_unknown_not_zero(monkeypatch):
    class _R:
        stdout = "not json at all"

    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    assert fp._served_pages("x") is None, (
        "a parse failure must not read as 'serves nothing', which would "
        "silently refuse every package instead of reporting a broken lookup")


def test_the_restriction_reason_is_this_tools_own(monkeypatch):
    """`--unfreeze` lifts only restrictions this tool set. The reason string
    is the only thing distinguishing them from one a person set by hand."""
    assert "DMA Insights" in fp.REASON
    assert fp._frozen({"contentRestrictions": [{"readOnly": True,
                                                "reason": fp.REASON}]})
    assert fp._frozen({"contentRestrictions": [{"readOnly": False}]}) is None
    assert fp._frozen({}) is None


def test_file_choice_is_the_workers_and_not_re_implemented():
    """The first version chose files itself and chose wrong. Nothing in this
    module may decide which copy is current."""
    src = Path(fp.__file__).read_text(encoding="utf-8")
    assert "_package_groups" in src, "grouping must be imported, not rebuilt"
    assert "modifiedTime\"]) > (rank" not in src, (
        "a local tie-break has crept back in; the worker's is the only one")


# ------------------------------------------------------- recording map

def test_the_recording_map_is_generated_and_current():
    """The map joins workbook TABS to page SECTIONS. It is generated from the
    worker's `_TAB_TARGET` and the live page contracts; a hand-edited copy is
    one refactor away from being confidently wrong, so this asserts it still
    matches the tab map it was generated from."""
    import json
    import sys as _s
    from pathlib import Path as _P

    repo = _P(fp.__file__).resolve().parents[3]
    _s.path.insert(0, str(repo / "apps" / "worker"))
    from dma_worker.workbook_parser import _TAB_TARGET

    doc = json.loads((repo / "plugins" / "dma-insights" / "references"
                      / "tab_recording_map.json").read_text(encoding="utf-8"))
    assert "GENERATED" in doc["_readme"][0]
    assert {r["tab"] for r in doc["tabs"]} == set(_TAB_TARGET), (
        "the recording map has drifted from _TAB_TARGET — re-run "
        "scripts/gen_recording_map.py")


def test_every_binding_carries_its_confidence():
    """`_TAB_TARGET` marks a mapping `verified` (checked field-by-field
    against get_page_contract) or `proposed` (read off the tab's shape). An
    agent relying on a proposed binding should know it is a reading, not a
    promise, so the map must never drop that column."""
    import json
    from pathlib import Path as _P

    repo = _P(fp.__file__).resolve().parents[3]
    doc = json.loads((repo / "plugins" / "dma-insights" / "references"
                      / "tab_recording_map.json").read_text(encoding="utf-8"))
    # `not_client_facing` is the third value the parser uses, for run config
    # and provenance tabs that feed no client surface. A test that allowed
    # only verified/proposed asserted a vocabulary the code does not have.
    for r in doc["tabs"]:
        assert r["confidence"] in ("verified", "proposed",
                                   "not_client_facing", "unstated"), r
    assert doc["counts"]["verified_bindings"] >= 1
    assert doc["counts"]["not_client_facing"] >= 1


def test_a_bound_row_names_a_real_section():
    """A binding that names a section the contract does not declare would
    send a producer to write into a field that will be dropped."""
    import json
    from pathlib import Path as _P

    repo = _P(fp.__file__).resolve().parents[3]
    doc = json.loads((repo / "plugins" / "dma-insights" / "references"
                      / "tab_recording_map.json").read_text(encoding="utf-8"))
    known = set(doc["sections"])
    for r in doc["tabs"]:
        if r["section"]:
            assert f"{r['page']}.{r['section']}" in known, r
