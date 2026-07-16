"""Tests for the cross-pillar aggregator (pure)."""
from __future__ import annotations

from app.services.cross_pillar import StoryRow, aggregate_cross_pillar


def _s(
    key: str,
    *,
    op: str = "P1",
    osid: str = "P1C1.1.1",
    cap: str | None = "Strategy",
    tp: str = "P2",
    themes: list[str] | None = None,
) -> StoryRow:
    return StoryRow(
        story_key=key,
        origin_pillar=op,
        origin_subcap_id=osid,
        origin_capability=cap,
        target_pillar=tp,
        themes=themes if themes is not None else ["Customer 360"],
    )


class TestAggregateCrossPillar:
    def test_groups_by_theme(self) -> None:
        stories = [
            _s("s1", themes=["Customer 360"]),
            _s("s2", themes=["Customer 360"]),
            _s("s3", themes=["Risk & Resilience"]),
        ]
        report = aggregate_cross_pillar(stories)
        assert report.total_stories == 3
        # Most-linked theme first
        assert report.themes[0].theme == "Customer 360"
        assert report.themes[0].story_count == 2
        assert report.themes[1].theme == "Risk & Resilience"

    def test_story_with_multiple_themes_appears_in_each(self) -> None:
        stories = [
            _s("s1", themes=["Customer 360", "Data Cloud"]),
        ]
        report = aggregate_cross_pillar(stories)
        themes = {t.theme for t in report.themes}
        assert themes == {"Customer 360", "Data Cloud"}
        # total_stories counts the row once even though it lands in 2 themes
        assert report.total_stories == 1

    def test_untagged_theme_for_empty_themes(self) -> None:
        stories = [_s("s1", themes=[])]
        report = aggregate_cross_pillar(stories)
        assert report.themes[0].theme == "(untagged)"

    def test_target_pillars_counted_per_theme(self) -> None:
        stories = [
            _s("s1", tp="P2", themes=["Customer 360"]),
            _s("s2", tp="P4", themes=["Customer 360"]),
            _s("s3", tp="P4", themes=["Customer 360"]),
        ]
        report = aggregate_cross_pillar(stories)
        cluster = report.themes[0]
        assert cluster.target_pillars == {"P2": 1, "P4": 2}

    def test_origin_capabilities_deduplicated_and_sorted(self) -> None:
        stories = [
            _s("s1", cap="Strategy"),
            _s("s2", cap="Strategy"),
            _s("s3", cap="Acquisition"),
        ]
        report = aggregate_cross_pillar(stories)
        assert report.themes[0].origin_capabilities == ["Acquisition", "Strategy"]

    def test_entity_filter_only_includes_intersecting_subcaps(self) -> None:
        stories = [
            _s("s1", osid="P1C1.1.1"),
            _s("s2", osid="P2C2.1.1"),
            _s("s3", osid="P3C3.1.1"),
        ]
        report = aggregate_cross_pillar(
            stories,
            entity_scored_subcap_ids={"P1C1.1.1", "P3C3.1.1"},
        )
        # s2 is filtered out; total reflects 2 stories
        assert report.total_stories == 2

    def test_empty_input_returns_empty_report(self) -> None:
        report = aggregate_cross_pillar([])
        assert report.total_stories == 0
        assert report.themes == []

    def test_ties_broken_alphabetically_by_theme(self) -> None:
        stories = [
            _s("s1", themes=["Zeta"]),
            _s("s2", themes=["Alpha"]),
        ]
        report = aggregate_cross_pillar(stories)
        # Both have story_count=1, so alpha sort kicks in
        assert [t.theme for t in report.themes] == ["Alpha", "Zeta"]
