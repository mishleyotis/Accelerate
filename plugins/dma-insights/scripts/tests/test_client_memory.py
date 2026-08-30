"""The per-client memory file: one per client, sections mirror the surfaces.

Owner instruction, 2026-08-20, pinned here: research outputs and package
synthesis must not get lost; one md file PER CLIENT, never one for all;
sections mirror the agent surfaces. The skeleton is generated from the same
served-sections census the coverage test enforces owners for, so a surface
added to the census automatically gets a memory section — the two cannot
drift apart.
"""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import client_memory  # noqa: E402


def test_skeleton_mirrors_the_served_census():
    text = client_memory.skeleton("baxter-credit-union-bcu", "Baxter")
    census = json.loads((HERE.parent / "fixtures"
                         / "served_sections.json").read_text())
    for page, names in census["pages"].items():
        for name in names:
            assert f"## {page}.{name}" in text, (
                f"served surface {page}.{name} has no memory section")
    for name, _ in client_memory.WORKING_SECTIONS:
        assert f"## {name}" in text


def test_excluded_surfaces_get_no_section():
    text = client_memory.skeleton("baxter-credit-union-bcu")
    assert "## overview.ceilings" not in text
    assert "## overview.evidence_coverage" not in text


def test_one_file_per_client_never_one_for_all(tmp_path):
    a = client_memory.memory_path("baxter-credit-union-bcu", str(tmp_path))
    b = client_memory.memory_path("logix-federal-credit-union", str(tmp_path))
    assert a != b and a.name.startswith("baxter") and b.name.startswith("logix")


def test_note_lands_under_its_section_newest_first(tmp_path):
    p = tmp_path / "c.md"
    p.write_text(client_memory.skeleton("c-client"))
    body = client_memory.add_note(p.read_text(), "overview.why_now",
                                  "older entry", "run11111111")
    body = client_memory.add_note(body, "overview.why_now",
                                  "newer entry", "run22222222")
    section = body.split("## overview.why_now")[1].split("## ")[0]
    assert section.index("newer entry") < section.index("older entry")
    assert "run22222" in section
    # the neighbouring section is untouched
    assert "_no entries yet_" in body.split("## overview.thought_leadership")[1].split("## ")[0]


def test_a_note_to_a_nonexistent_section_refuses():
    text = client_memory.skeleton("c-client")
    with pytest.raises(SystemExit):
        client_memory.add_note(text, "overview.invented_surface", "x", None)


def test_slug_discipline_rejects_free_text():
    with pytest.raises(SystemExit):
        client_memory.memory_path("Baxter Credit Union!", "/tmp")


def test_no_hashtag_numbering_in_the_template():
    """The owner's no-hashtags rule applies to what we generate too."""
    import re
    assert not re.search(r"#\d", client_memory.skeleton("c-client"))
