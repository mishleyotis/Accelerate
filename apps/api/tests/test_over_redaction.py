"""Over-redaction: a producer's `internal_only` may not hide a field the
rulebook says the client is owed, unless it says why (RC-08 / D-11).

MEASURED 2026-10-04 on SWBC (gold audit, slice PL-04): the producer marked
`platforms[*].estate_reach` and `platforms[*].integration_pathway`
internal_only. The rulebook's exclusion set for platform_story is
`zennify_pathway` alone, and customer_allowlist.json allows both fields, so
the customer DD-11 showed neither on any tile — and nothing noticed, because
every redaction test guards against LEAKS and none against a hole.

The rule served here: a path in CUSTOMER_SHAREABLE marked internal_only with
no `why` is NOT applied for the customer, and the receipt names it under
`over_redaction_ignored`. A marking written as {"path": ..., "why": ...}
is a documented withholding and is honoured. Every other net — vendor name,
seller voice, machinery, pipeline vocabulary, the allowlist — still runs over
the field, so seller remarks belong in zennify_pathway, which is always
stripped.

Also pinned: a dict-shaped marking used to be SKIPPED by the walker (it
accepted strings only), which is fail-open; it now strips its `path`.
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.redaction import CUSTOMER_SHAREABLE, redact_section  # noqa: E402

TILE = {"name": "Platform A", "rank": 1,
        "estate_reach": {"summary": "Reaches the servicing and origination "
                                    "estate through the existing core."},
        "integration_pathway": "Through the core's published APIs.",
        "zennify_pathway": "Our delivery approach for this tile.",
        "story_md": "Why this platform first."}
BODY = {"platforms": [copy.deepcopy(TILE), copy.deepcopy(TILE)]}
MARKED = ["platforms[*].estate_reach", "platforms[*].integration_pathway"]


def test_swbc_shape_estate_reach_marking_is_flagged_and_not_applied():
    out, rep = redact_section("platform", "platform_story",
                              copy.deepcopy(BODY), MARKED, "customer")
    for p in out["platforms"]:
        assert p["estate_reach"]["summary"]
        assert p["integration_pathway"]
        assert "zennify_pathway" not in p          # the real exclusion holds
    assert sorted(rep["over_redaction_ignored"]) == sorted(MARKED)


def test_index_and_section_qualified_spellings_are_recognised():
    marks = ["platform_story.platforms[0].estate_reach",
             "platforms.integration_pathway"]
    out, rep = redact_section("platform", "platform_story",
                              copy.deepcopy(BODY), marks, "customer")
    assert all("estate_reach" in p and "integration_pathway" in p
               for p in out["platforms"])
    assert len(rep["over_redaction_ignored"]) == 2


def test_a_documented_withholding_is_honoured():
    marks = [{"path": "platforms[*].estate_reach",
              "why": "names a client system under NDA"}]
    out, rep = redact_section("platform", "platform_story",
                              copy.deepcopy(BODY), marks, "customer")
    assert all("estate_reach" not in p for p in out["platforms"])
    assert rep["over_redaction_ignored"] == []


def test_a_dict_marking_without_why_on_an_ordinary_path_still_strips():
    """Fail-closed: the walker used to skip anything that was not a str."""
    marks = [{"path": "platforms[*].story_md"}]
    out, _ = redact_section("platform", "platform_story",
                            copy.deepcopy(BODY), marks, "customer")
    assert all("story_md" not in p for p in out["platforms"])


def test_marking_a_whole_tile_is_not_second_guessed():
    out, rep = redact_section("platform", "platform_story",
                              copy.deepcopy(BODY), ["platforms[1]"],
                              "customer")
    assert len(out["platforms"]) == 1 and rep["over_redaction_ignored"] == []


def test_the_shareable_set_is_inside_the_allowlist():
    """A shareable path the allowlist then drops would be a promise the serve
    layer cannot keep."""
    import json
    allow = json.loads((ROOT / "apps" / "api" / "dma_api"
                        / "customer_allowlist.json").read_text())["sections"]
    for (page, section), paths in CUSTOMER_SHAREABLE.items():
        spec = allow[f"{page}.{section}"]
        for p in paths:
            field, _, key = p.partition("[*].")
            assert key in spec["items"][field], (page, section, p)
