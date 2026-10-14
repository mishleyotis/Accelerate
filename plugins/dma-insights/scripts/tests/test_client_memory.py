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


# ── F-G05-017 · locked, versioned, capped ────────────────────────────────

def test_write_note_is_versioned_and_refuses_a_stale_version(tmp_path):
    p = tmp_path / "c-client.md"
    out = client_memory.write_note(p, "overview.why_now", "first", "run11111111", client="c-client")
    assert out["version"] == client_memory.version_of(p.read_text(encoding="utf-8"))
    assert out["previous"] == client_memory.version_of(client_memory.skeleton("c-client"))
    v = out["version"]
    with pytest.raises(SystemExit, match="version mismatch"):
        client_memory.write_note(p, "overview.why_now", "second", None, expect_version="deadbeefdeadbeef")
    assert "second" not in p.read_text()
    out2 = client_memory.write_note(p, "overview.why_now", "second", None, expect_version=v)
    assert out2["previous"] == v and "second" in p.read_text()
    assert not (tmp_path / "c-client.md.tmp").exists()


def test_the_cap_is_stated_and_refuses(tmp_path):
    p = tmp_path / "c-client.md"
    p.write_text(client_memory.skeleton("c-client") + "\n" + ("x" * client_memory.CAP_BYTES))
    with pytest.raises(SystemExit, match="cap"):
        client_memory.write_note(p, "overview.why_now", "one more", None)
    assert client_memory.size_of(p)["over_cap"]
    q = tmp_path / "d-client.md"
    q.write_text(client_memory.skeleton("d-client") + "\n" + ("x" * int(client_memory.CAP_BYTES * 0.85)))
    out = client_memory.write_note(q, "overview.why_now", "still fits", None)
    assert out["consolidate_due"] is True


def test_the_cli_prints_the_version_and_honours_expect_version(tmp_path, capsys):
    d = str(tmp_path)
    assert client_memory.main(["note", "--client", "c-client", "--section", "overview.why_now",
                               "--text", "hello", "--dir", d]) == 0
    line = capsys.readouterr().out
    assert "version " in line and "% of cap" in line
    assert client_memory.main(["version", "--client", "c-client", "--dir", d]) == 0
    v = json.loads(capsys.readouterr().out)["version"]
    with pytest.raises(SystemExit):
        client_memory.main(["note", "--client", "c-client", "--section", "overview.why_now",
                            "--text", "again", "--dir", d, "--expect-version", "0000000000000000"])
    assert client_memory.main(["note", "--client", "c-client", "--section", "overview.why_now",
                               "--text", "again", "--dir", d, "--expect-version", v]) == 0
