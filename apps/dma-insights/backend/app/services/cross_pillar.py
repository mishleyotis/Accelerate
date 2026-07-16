"""Cross-pillar story service — exposes the catalogue's
`ccg_cross_pillar_stories` table as themed cards for D5 Context.

Per plan §②: cross-pillar stories link insights and themes that span
multiple pillars (e.g. a Data Cloud rollout that touches P2 Engagement
+ P4 Data & AI). The catalogue ships these per-(story, target_pillar)
with `themes[]` arrays.

This pure helper groups stories by theme + filters to an entity's
profile (only stories whose origin_subcap_id intersects with the
entity's scored subcaps). The router below composes it with the
session + catalogue version.

State-branch contract:
  - Entity has no ACTIVE run     → no stories returned
  - Run scored, but no
    intersection with cross-
    pillar story origins         → empty list (UI shows "No
                                   cross-pillar themes for this run")
  - Stories present              → grouped by theme with
                                   target_pillars counts so the AE sees
                                   which pillars are most cross-linked
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class StoryRow:
    """One cross-pillar story link (from ccg_cross_pillar_stories)."""
    story_key: str
    origin_pillar: str
    origin_subcap_id: str
    origin_capability: str | None
    target_pillar: str
    themes: list[str]


@dataclass
class ThemeCluster:
    """Aggregated view of all stories under one theme."""
    theme: str
    story_count: int
    target_pillars: dict[str, int]    # target_pillar → number of links
    origin_capabilities: list[str]    # de-duplicated, sorted


@dataclass
class CrossPillarReport:
    themes: list[ThemeCluster] = field(default_factory=list)
    total_stories: int = 0


def aggregate_cross_pillar(
    stories: Iterable[StoryRow],
    *,
    entity_scored_subcap_ids: set[str] | None = None,
) -> CrossPillarReport:
    """Group stories by theme, optionally filtering to an entity's
    scored subcaps so D5 Context only shows stories the AE can act on.
    """
    by_theme: dict[str, list[StoryRow]] = {}
    total = 0
    for story in stories:
        if entity_scored_subcap_ids is not None and \
                story.origin_subcap_id not in entity_scored_subcap_ids:
            continue
        total += 1
        # A story can carry multiple themes → it appears in each cluster
        for theme in story.themes or ["(untagged)"]:
            by_theme.setdefault(theme, []).append(story)

    report = CrossPillarReport(total_stories=total)
    for theme in sorted(by_theme.keys()):
        rows = by_theme[theme]
        pillars: dict[str, int] = {}
        caps: set[str] = set()
        for row in rows:
            pillars[row.target_pillar] = pillars.get(row.target_pillar, 0) + 1
            if row.origin_capability:
                caps.add(row.origin_capability)
        report.themes.append(
            ThemeCluster(
                theme=theme,
                story_count=len(rows),
                target_pillars=dict(sorted(pillars.items())),
                origin_capabilities=sorted(caps),
            )
        )
    # Order clusters by story_count desc (most-linked themes first)
    report.themes.sort(key=lambda t: (-t.story_count, t.theme))
    return report
