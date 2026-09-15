"""The per-surface map and the role table must not drift apart.

TWO ARTEFACTS SAY WHICH CONNECTOR RESEARCHES A SURFACE, and until now
nothing compared them:

    docs/CONNECTORS.md              payload section -> connector families
    scripts/provision_agent_tools.py  role -> connector families, written
                                      into every manifest's `tools:`

Measured 2026-08-30: the table assigned Explorium to
`overview.firmographics`, `overview.leadership`, `insights.landscape`,
`platform.platform_story` and `techstack.techstack`, while the `production`
default granted exa/tavily/clay/quartr/drive and NOT ONE web-app surface
producer declared `mcp__Vibe_Prospecting__`. An agent that does not DECLARE
a tool cannot call it, whatever the harness binds and whatever the
permission layer allows — so the doc said Explorium verifies the
technographic register while the agent that writes that register had no way
to ask Explorium anything.

This is a CHECKER, not a second writer. `provision_agent_tools.py` owns the
role table and writes the front matter; this re-derives what the doc
requires and fails if the manifests do not satisfy it. A second writer with
its own table would be the same drift one level up — which is why the first
version of this work, which shipped exactly that, was deleted.

THE JOIN IS DERIVED. CONNECTORS.md gives section -> families; each
producer's `description` names the sections it owns. Nothing here is typed
by hand, so a section that moves between producers fails here rather than
going quiet.

2026-09-14: connectors moved to the orchestrator tier (owner decision — the
harness binds none of them into a headless child, so a producer holding Exa
held a refusal). A family in the table is now satisfied when the OWNER holds
it OR a SERVICING agent does — the conductor and the two enrichment
specialists, which service the `search_requests` a producer emits. A `‡`
suffix on a family in the table means the owner must hold it ITSELF: the
surface is written FROM the connector's answer (Clay contacts, the Explorium
register), not corroborated by it.
"""
import re
from collections import defaultdict
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
PLUGIN = HERE.parents[2]
AGENTS = PLUGIN / "agents"
CONNECTORS_DOC = PLUGIN / "docs" / "CONNECTORS.md"

#: Prose name in CONNECTORS.md -> the mcp family that implements it.
FAMILY_OF = {
    "clay": "Clay", "exa": "Exa", "tavily": "Tavily",
    "explorium": "Vibe_Prospecting", "vibe-prospecting": "Vibe_Prospecting",
    "indeed": "Indeed", "quartr": "Quartr",
}

#: Only these tiers RESEARCH a section. An auditor and a producer both NAME
#: the sections they deal with, so matching on mention alone proposed
#: granting Clay, Indeed and Explorium to evidence-integrity-checker,
#: exclusion-boundary-auditor, numeric-reconciliation-checker and
#: deployed-app-auditor — four read-only agents whose whole value is that
#: they cannot reach outside the run they judge. Widening a checker's tool
#: surface to satisfy a mapping is how a safeguard becomes a participant.
RESEARCHING_TIERS = ("production", "research")

#: The agents that CALL a connector on a producer's behalf. A family the
#: table assigns to a section without ‡ is satisfied when one of these holds
#: it, because the producer emits the query and one of these services it.
SERVICING = ("research/research-conductor.md",
             "enrichment/enrichment-connector-specialist.md",
             "enrichment/enrichment-web-specialist.md")


def manifests():
    return [p for p in sorted(AGENTS.rglob("*.md")) if p.name != "README.md"]


def tools_line(path: Path) -> str:
    m = re.search(r"^tools:(.*)$", path.read_text(encoding="utf-8")[:8000], re.M)
    return m.group(1) if m else ""


def section_families() -> dict:
    """payload section -> {family}, from the CONNECTORS.md per-surface table."""
    return {k: set(v) for k, v in section_requirements().items()}


def section_requirements() -> dict:
    """payload section -> {family: owner_must_hold}. `‡` after a family name
    in the table means the owner itself must hold it; without it a servicing
    agent may."""
    out = {}
    for line in CONNECTORS_DOC.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*([a-z_]+\.[a-z_]+)\s*\|([^|]*)\|", line)
        if not m:
            continue
        fams = {}
        for w, mark in re.findall(r"([A-Za-z-]+)(‡?)", m.group(2)):
            if w.lower() in FAMILY_OF:
                fam = FAMILY_OF[w.lower()]
                fams[fam] = fams.get(fam, False) or bool(mark)
        if fams:
            out[m.group(1)] = fams
    return out


def servicing_families() -> set:
    out = set()
    for rel in SERVICING:
        line = tools_line(AGENTS / rel)
        out |= set(re.findall(r"mcp__([A-Za-z0-9_-]+)__", line))
    return out


def owners(section: str) -> list:
    """Manifests whose DESCRIPTION claims this section.

    The description is where a producer states what it owns, so it is a
    claim rather than a mention: heatmap-grid-producer names
    `heatmap.cell_evidence` in prose while owning only
    `heatmap.workbook_scores`, and matching the body would have granted it
    Indeed for a surface it does not write.
    """
    out = []
    for p in manifests():
        if p.relative_to(AGENTS).parts[0] not in RESEARCHING_TIERS:
            continue
        head = p.read_text(encoding="utf-8")[:8000]
        m = re.search(r"^description:(.*?)(?=^[a-z_]+:)", head, re.M | re.S)
        if m and section in m.group(1):
            out.append(p)
    return out


def test_the_surface_map_is_still_parseable():
    """Floor assertion: an unparsed table makes every check below vacuous."""
    fams = section_families()
    assert len(fams) >= 15, (
        f"only {len(fams)} section(s) parsed out of CONNECTORS.md — the table "
        f"changed shape and this join is no longer reading it")
    assert "Vibe_Prospecting" in fams.get("techstack.techstack", set()), (
        "Explorium is the charter's mandated technographic source (REQ-A); "
        "if the table stopped saying so, that is the thing to look at")


def test_every_producer_declares_the_connectors_its_section_needs():
    """The defect itself, re-derived from both halves on every run: a family
    the table assigns is held by the owner, or (without ‡) by a servicing
    agent that calls it on the owner's behalf."""
    served = servicing_families()
    missing = defaultdict(set)
    for section, fams in section_requirements().items():
        for p in owners(section):
            line = tools_line(p)
            for fam, owner_must_hold in fams.items():
                if f"mcp__{fam}__" in line:
                    continue
                if not owner_must_hold and fam in served:
                    continue
                missing[p.name].add(
                    f"{fam} (for {section}{', ‡ owner must hold it' if owner_must_hold else ''})")
    assert not missing, (
        "producers own a section whose connector nobody can call for them — "
        "fix the ROLE TABLE in scripts/provision_agent_tools.py and re-run it "
        f"with --write, never the manifest by hand: "
        f"{ {k: sorted(v) for k, v in missing.items()} }")


def test_the_servicing_tier_holds_every_family_it_is_relied_on_for():
    """A family without ‡ anywhere in the table is one a servicing agent must
    hold — otherwise the table promises a source nobody in the pipeline can
    reach for that surface."""
    needed = set()
    for fams in section_requirements().values():
        needed |= {f for f, must in fams.items() if not must}
    assert needed <= servicing_families(), (
        f"no servicing agent holds {sorted(needed - servicing_families())}")


def test_the_dagger_marks_are_parsed_and_mean_the_owner():
    """Floor: the ‡ grammar is read. techstack and leadership are the two
    surfaces WRITTEN from a connector's answer, so they carry it."""
    req = section_requirements()
    assert req["techstack.techstack"].get("Vibe_Prospecting") is True
    assert req["overview.leadership"].get("Clay") is True
    assert req["insights.landscape"].get("Vibe_Prospecting") is True
    assert req["heatmap.cell_evidence"].get("Exa") is False, (
        "cell_evidence is corroborated through the orchestrator tier, not "
        "written from a connector")


def test_read_only_checkers_are_never_granted_enrichment():
    """The safety property. An adversary that can reach outside the run it
    is judging is a participant, not an adversary."""
    for name in ("evidence-integrity-checker", "exclusion-boundary-auditor",
                 "numeric-reconciliation-checker", "deployed-app-auditor"):
        for p in (x for x in manifests() if x.stem == name):
            line = tools_line(p)
            assert line, f"{name} declares no tools line"
            for banned in ("mcp__Clay__", "mcp__Indeed__",
                           "mcp__Vibe_Prospecting__"):
                assert banned not in line, (
                    f"{name} declares {banned} — it is a read-only checker "
                    f"and enrichment reach turns it from a judge into a "
                    f"participant")


def test_there_is_exactly_one_writer_of_agent_tools():
    """Two provisioners with two tables is the same drift one level up.

    The first version of this work shipped a second writer under
    plugins/dma-insights/scripts/ with its own derivation, which immediately
    disagreed with the role table and failed the existing provisioning test.
    It was deleted; this pins that it stays deleted.
    """
    writers = [p for p in (PLUGIN / "scripts").glob("provision*.py")]
    assert not writers, (
        f"{[p.name for p in writers]} provisions agent tools alongside "
        f"scripts/provision_agent_tools.py — one table, one writer")
    assert (PLUGIN.parents[1] / "scripts" / "provision_agent_tools.py").exists()


def test_explorium_reaches_every_surface_the_charter_gives_it():
    """REQ-A puts the technographic estate on Explorium and Clay."""
    for section in ("techstack.techstack", "insights.landscape"):
        got = owners(section)
        assert got, f"no producer claims {section} in its description"
        for p in got:
            assert "mcp__Vibe_Prospecting__" in tools_line(p), (
                f"{p.name} owns {section}, which CONNECTORS.md sources from "
                f"Explorium, and cannot call it")
