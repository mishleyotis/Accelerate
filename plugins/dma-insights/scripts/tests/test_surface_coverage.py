"""Every payload path the live app serves has a named owning agent.

The complaint that produced this test (user, 2026-08-20): "I see most pages
having 1 assigned agent eg platform page which has multiple surfaces; ensure
every path to be written into is considered." Coverage claimed in prose rots
the moment a surface is added; coverage joined from data cannot.

The join, all three legs measured rather than asserted:

  fixtures/served_sections.json      what production actually served for the
                                     gold-standard client (Baxter run c1351d25,
                                     internal audience) — regenerated only from
                                     a live fetch, never edited by hand
    -> surface-map.md                the census with owners: every spec surface,
                                     its payload section(s), its producing agent
    -> agents/<owner>.md             the owner must exist as a file, not a name

A served section no map row claims, a map owner with no agent file, or an
excluded section that leaks back into the census each fail loudly. A row the
map marks "server-computed — no producer" is a considered path, not an orphan
(H9 value chain: the producer submits the envelope, the app joins the rows).

The excluded block mirrors an owner adjudication (2026-08-20): ceilings and
evidence_coverage left the live payload. The API enforces that as NEVER_SERVED
in apps/api/dma_api/redaction.py; this test pins the plugin's census and the
API's allowlist to each other so they cannot drift apart silently.
"""
import json
import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2]
REPO = PLUGIN.parents[1]
FIXTURE = PLUGIN / "fixtures" / "served_sections.json"
SURFACE_MAP = (PLUGIN / "skills" / "dma-surface-production" / "05-lifecycle"
               / "surface-map.md")
AGENTS_DIR = PLUGIN / "agents"
REDACTION = REPO / "apps" / "api" / "dma_api" / "redaction.py"

_SECTION_RE = re.compile(
    r"\b(overview|heatmap|insights|platform|context|techstack)\.([a-z_]+)\b")
# Roster names end in a role suffix; prose kebab words ("server-computed",
# "envelope-only") do not, so the suffix is the discriminator.
_OWNER_RE = re.compile(
    r"\b([a-z][a-z0-9-]*-(?:producer|consolidator|verifier|challenger|vetter|"
    r"auditor|overseer|rectifier|grader|testgen))\b")
_SERVER_COMPUTED = "server-computed"


def load_census() -> dict:
    return json.loads(FIXTURE.read_text())


def parse_surface_map(text: str) -> dict:
    """payload section -> {"owners": set of agent names, "server_computed": bool}.

    Reads every pipe-table row that names at least one payload section, so the
    parser survives the map being rewritten as long as rows keep carrying a
    producing agent and a payload section — which is what makes them rows.
    """
    claims: dict = {}
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        sections = {f"{page}.{name}" for page, name
                    in _SECTION_RE.findall(line)}
        if not sections:
            continue
        owners = set(_OWNER_RE.findall(line))
        server_computed = _SERVER_COMPUTED in line
        for section in sections:
            entry = claims.setdefault(
                section, {"owners": set(), "server_computed": False})
            entry["owners"] |= owners
            entry["server_computed"] = (entry["server_computed"]
                                        or server_computed)
    return claims


def find_orphans(census: dict, claims: dict) -> list:
    """Served sections with no owning agent file and no server-computed row."""
    orphans = []
    for page, sections in census["pages"].items():
        for name in sections:
            section = f"{page}.{name}"
            entry = claims.get(section)
            if entry is None:
                orphans.append(f"{section}: no surface-map row claims it")
                continue
            live = {o for o in entry["owners"]
                    if any(AGENTS_DIR.rglob(f"{o}.md"))}
            if not live and not entry["server_computed"]:
                named = ", ".join(sorted(entry["owners"])) or "nobody"
                orphans.append(
                    f"{section}: owned by {named}, but no such agent file "
                    f"exists under agents/")
    return orphans


@pytest.fixture(scope="module")
def census():
    return load_census()


@pytest.fixture(scope="module")
def claims():
    return parse_surface_map(SURFACE_MAP.read_text())


def test_every_served_section_has_a_living_owner(census, claims):
    orphans = find_orphans(census, claims)
    assert not orphans, (
        "Served payload sections without a considered write path:\n  "
        + "\n  ".join(orphans))


def test_named_owners_all_exist_as_agent_files(claims):
    """A map row naming a dead agent is a lie even when a sibling covers it."""
    dead = sorted({owner
                   for entry in claims.values()
                   for owner in entry["owners"]
                   if not any(AGENTS_DIR.rglob(f"{owner}.md"))})
    assert not dead, (
        "surface-map.md names producing agents that do not exist: "
        + ", ".join(dead))


def test_the_check_can_fail(census, claims):
    """Negative control: a fabricated section must be reported as an orphan."""
    fabricated = json.loads(json.dumps(census))
    fabricated["pages"]["overview"].append("a_section_nobody_serves")
    orphans = find_orphans(fabricated, claims)
    assert any("a_section_nobody_serves" in o for o in orphans)


def test_excluded_sections_stay_out_of_the_census(census):
    for page, names in census["excluded"].items():
        if page.startswith("_"):
            continue
        for name in names:
            assert name not in census["pages"].get(page, []), (
                f"{page}.{name} is excluded by owner adjudication but is "
                f"back in the served census — regenerate from a live fetch "
                f"and check the API deploy")


def test_exclusions_match_the_api_never_served_allowlist(census):
    """The plugin census and the serving boundary must agree, both ways."""
    text = REDACTION.read_text()
    block = text[text.index("NEVER_SERVED = frozenset(("):]
    block = block[:block.index("))")]
    api_side = set(re.findall(r'\("([a-z_]+)",\s*"([a-z_]+)"\)', block))
    census_side = {(page, name)
                   for page, names in census["excluded"].items()
                   if not page.startswith("_")
                   for name in names}
    assert census_side == api_side, (
        f"excluded-surface drift: census says {sorted(census_side)}, "
        f"API NEVER_SERVED says {sorted(api_side)}")


def test_every_agent_is_reachable_from_the_routing_authority():
    """routing.md is where the SessionStart hook points every session, and
    what the routine prompt calls the routing authority. An agent the file
    never names is one no session will ever dispatch — it ships, it is
    listed in the manifest, and it is dead.

    Measured 2026-08-20: nine of forty-seven were absent, including all
    three pre-submit checkers (evidence integrity, numeric reconciliation,
    exclusion boundary) that the routine prompt itself instructs sessions to
    run. The prompt named them; the authority it pointed at did not.
    """
    import yaml

    agents_dir = PLUGIN / "agents"
    routing = (PLUGIN / "skills" / "dma-surface-production" /
               "05-lifecycle" / "routing.md").read_text()
    names = []
    for f in sorted(agents_dir.rglob("*.md")):
        front = f.read_text().split("---", 2)[1]
        names.append(yaml.safe_load(front)["name"])
    missing = [n for n in names if n not in routing]
    assert not missing, (
        f"{len(missing)} of {len(names)} agents are not named in routing.md, "
        f"so no session can route to them: {missing}")


def test_every_agent_front_matter_parses_as_yaml():
    """A description carrying an unquoted colon ('Read-only: it repairs
    nothing') makes YAML read a mapping where a sentence was meant, and the
    agent's front-matter does not parse at all. Four agents shipped that way
    until 2026-08-20; string-splitting checks could not see it, so this one
    uses the parser."""
    import yaml

    broken = []
    for f in sorted((PLUGIN / "agents").rglob("*.md")):
        txt = f.read_text()
        if not txt.startswith("---"):
            broken.append((f.name, "no front-matter"))
            continue
        try:
            d = yaml.safe_load(txt.split("---", 2)[1])
        except Exception as e:                               # noqa: BLE001
            broken.append((f.name, f"{type(e).__name__}: {str(e)[:80]}"))
            continue
        if not isinstance(d, dict) or "name" not in d or "description" not in d:
            broken.append((f.name, "front-matter lacks name/description"))
    assert not broken, f"agent front-matter does not parse: {broken}"
