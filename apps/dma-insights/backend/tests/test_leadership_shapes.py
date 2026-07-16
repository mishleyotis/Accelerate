"""Leadership extraction across the real corpus shapes.

The 2026-06-23 audit found `extract_leadership` reaching only 4/113 packages
because `_find_rosters` recognised a roster only when it was a LIST under a
narrow set of keys. Real packages carry the roster as:
  - a DICT of roles → person dicts  (`leadership_snapshot`, entity_profile.json)
  - a DICT of roles → person STRINGS (`{"ceo": "Jane Doe (President & CEO)"}`)
  - a LIST of dicts under `leadership_contacts` / `key_leadership`
"""
from __future__ import annotations

import json

from app.services.entity_healing import _find_rosters, extract_leadership


def _names(rosters) -> set[str]:
    out: set[str] = set()
    for roster in rosters:
        for person in roster:
            for k, v in person.items():
                if k.lower() in ("name", "full_name") and isinstance(v, str):
                    out.add(v)
    return out


class TestFindRosters:
    def test_dict_of_roles_with_person_dicts(self) -> None:
        blob = {
            "leadership_snapshot": {
                "ceo": {"name": "Rick L. Sowers", "title": "President & CEO"},
                "cfo": {"name": "Cory Stewart", "title": "CFO"},
            }
        }
        assert _names(_find_rosters(blob)) == {"Rick L. Sowers", "Cory Stewart"}

    def test_dict_of_roles_with_string_values(self) -> None:
        blob = {"leadership": {
            "ceo": "William Mynatt Jr. (President & CEO)",
            "cfo": "Glen Braun (SVP & CFO)",
        }}
        rosters = list(_find_rosters(blob))
        people = [p for r in rosters for p in r]
        names = {p["name"] for p in people}
        assert names == {"William Mynatt Jr.", "Glen Braun"}
        # parenthetical becomes the title
        ceo = next(p for p in people if p["name"] == "William Mynatt Jr.")
        assert ceo["title"] == "President & CEO"

    def test_key_leadership_variant(self) -> None:
        blob = {"key_leadership": {"CEO": "Dominic Ng (Chairman & CEO)"}}
        assert _names(_find_rosters(blob)) == {"Dominic Ng"}

    def test_leadership_contacts_list_shape(self) -> None:
        blob = {"leadership_contacts": [
            {"name": "Ben Browning", "title": "Vice Chairman & CEO"},
        ]}
        assert _names(_find_rosters(blob)) == {"Ben Browning"}

    def test_multi_person_string_takes_first(self) -> None:
        blob = {"key_leadership": {"CDO": "Dominick Marchetti (Jul 2025) + Elijah Pallante (Jan 2022)"}}
        people = [p for r in _find_rosters(blob) for p in r]
        assert [p["name"] for p in people] == ["Dominick Marchetti"]

    def test_metadata_role_key_is_not_a_person(self) -> None:
        # Rockland's `ctoo_background` is prose, not a person — must be skipped.
        blob = {"leadership": {
            "ctoo": "Lee C. Powlus (Chief Technology and Operations Officer)",
            "ctoo_background": "Nearly 4 decades IT/digital transformation. Ex-SVP People's United.",
        }}
        names = {p["name"] for r in _find_rosters(blob) for p in r}
        assert names == {"Lee C. Powlus"}


class TestExtractLeadership:
    def test_reads_entity_profile_leadership_snapshot(self, tmp_path) -> None:
        (tmp_path / "08_appendices").mkdir(parents=True)
        (tmp_path / "08_appendices" / "entity_profile.json").write_text(json.dumps({
            "leadership_snapshot": {
                "ceo": {"name": "Rick L. Sowers", "title": "President & CEO",
                        "background": "UCSD Economics; ex-Accenture."},
                "cfo": {"name": "Cory Stewart", "title": "CFO"},
            }
        }))
        people = extract_leadership(tmp_path)
        names = {p["name"] for p in people}
        assert names == {"Rick L. Sowers", "Cory Stewart"}
        ceo = next(p for p in people if p["name"] == "Rick L. Sowers")
        assert ceo["title"] == "President & CEO"
        assert ceo["background"] and "Accenture" in ceo["background"]

    def test_reads_research_handoff_key_leadership_strings(self, tmp_path) -> None:
        (tmp_path / "02_research_workbook").mkdir(parents=True)
        (tmp_path / "02_research_workbook" / "research_handoff.json").write_text(json.dumps({
            "key_leadership": {
                "CEO": "James Kim (CEO)",
                "CTO": "Gary Henderson (CTO)",
            }
        }))
        names = {p["name"] for p in extract_leadership(tmp_path)}
        assert names == {"James Kim", "Gary Henderson"}

    def test_empty_when_no_roster(self, tmp_path) -> None:
        (tmp_path / "08_appendices").mkdir(parents=True)
        (tmp_path / "08_appendices" / "entity_profile.json").write_text(json.dumps({
            "legal_name": "Acme Bank", "total_assets": "1B",
        }))
        assert extract_leadership(tmp_path) == []


class TestDeriveLeadershipJsonBackfill:
    """F1: the in-place backfill (derive_leadership) reads the JSON dict-of-roles
    shapes via the same extractor as ingest, not just CSV/DOCX."""

    def test_json_leadership_reads_entity_profile_snapshot(self, tmp_path) -> None:
        from app.scripts.derive_leadership import _json_leadership
        (tmp_path / "08_appendices").mkdir(parents=True)
        (tmp_path / "08_appendices" / "entity_profile.json").write_text(json.dumps({
            "leadership_snapshot": {
                "ceo": {"name": "Rick L. Sowers", "title": "President & CEO"},
                "cfo": {"name": "Cory Stewart", "title": "CFO"},
            }
        }))
        people = _json_leadership(str(tmp_path))
        names = {p["name"] for p in people}
        assert names == {"Rick L. Sowers", "Cory Stewart"}
        # downstream shape: name/title/tenure/background keys present
        assert set(people[0]) >= {"name", "title", "tenure", "background"}

    def test_json_leadership_reads_research_handoff_key_leadership(self, tmp_path) -> None:
        from app.scripts.derive_leadership import _json_leadership
        (tmp_path / "02_research_workbook").mkdir(parents=True)
        (tmp_path / "02_research_workbook" / "research_handoff.json").write_text(json.dumps({
            "key_leadership": {"CEO": "Dominic Ng (Chairman & CEO)"}
        }))
        assert {p["name"] for p in _json_leadership(str(tmp_path))} == {"Dominic Ng"}

    def test_json_leadership_empty_when_no_roster(self, tmp_path) -> None:
        from app.scripts.derive_leadership import _json_leadership
        (tmp_path / "08_appendices").mkdir(parents=True)
        (tmp_path / "08_appendices" / "entity_profile.json").write_text(
            json.dumps({"legal_name": "Acme Bank"}))
        assert _json_leadership(str(tmp_path)) == []
