"""Two workbooks offer the same excerpt; the less-damaged one is stored.

MEM-0129 and MEM-0143. What actually reached T. Rowe Price's client-facing
heatmap was 1,964 of 2,063 evidence items cut mid-word — while a
480-character-per-clause copy of the same evidence sat in the same package,
unread. Two defects stacked to produce that, and both are fixed here.

FIRST, THE RESEARCH LEDGER NEVER READ ITS OWN EXCERPT COLUMN. The field was a
flat `None` with the comment "filled from the detail tabs below", which is
true of the generation that writes excerpts as a fact-tagged blob under
`Evidence_Excerpt` on a SubCap-anchored tab, and false of the one measured:
T. Rowe's `Evidence_Detail` is anchored on Evidence_ID and carries plain
`Excerpt` and `Anchor_Quote` columns — 1,642 values, longest 480. The parse
produced 0 excerpts from 1,642 and reported nothing.

SECOND, LENGTH WAS THE WRONG CRITERION, and measuring it proved so. The
scoring ledger offers 426 characters and the research workbook 434 — a
rounding apart. But the 426 is THREE clauses each cut at 140, reading
"…live in T. Row | Technog"; the 434 is ONE clause cut at 480, reading as a
sentence. Three fragments totalling more characters carry less of the source,
not more, and a producer reading fragments is the exact mechanism of
MEM-0129.
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]
                       / "packages" / "shared"))

from dma_worker.workbook_parser import parse_research_workbook  # noqa: E402
import excerpt_clip as clip                                     # noqa: E402


def cut(width: int, i: int) -> str:
    """A clause hard-clipped at `width`, ending mid-word, distinct per i —
    distinct matters, because the corpus check counts DISTINCT clauses and
    twenty copies of one string is not a spike."""
    body = (f"the vendor {i} deployed a platform across every region and the "
            f"filing describes the arrangement at length ") * 8
    out = body[:width - 6] + "Salesf"
    assert len(out) == width and out[-1].isalnum()
    return out


def clean(i: int) -> str:
    return (f"A filing sentence number {i} of ordinary length, ending as "
            f"sentences do.")


# ── the comparator ────────────────────────────────────────────────────

def test_the_wider_cut_wins_between_two_clipped_corpora():
    """480 keeps three and a half times as much of each sentence as 140."""
    narrow = clip.clip_signature([cut(140, i) + " | " + cut(140, i + 99)
                                  for i in range(20)])
    wide = clip.clip_signature([cut(480, i) for i in range(20)])
    assert narrow["verdict"] == "CLIPPED" and narrow["width"] == 140
    assert wide["verdict"] == "CLIPPED" and wide["width"] == 480
    assert clip.prefer(narrow, wide) > 0, "the 480 corpus must win"
    assert clip.prefer(wide, narrow) < 0, "and the comparison is symmetric"


def test_length_picks_the_narrower_cut_whenever_it_has_more_clauses():
    """Why severity and not length, stated as the real measurement rather
    than a synthetic coincidence.

    Over T. Rowe's 752 shared ids, the research (480) excerpt is longer for
    494 and the SCORING ledger (140) excerpt is longer for 258. So length
    gets it right two thirds of the time and wrong for 258 items — and the
    258 are wrong in the damaging direction, storing three or four fragments
    in place of one span. The principle below is what produces those 258:
    enough 140-cuts out-measure a single wider cut while carrying less of
    every sentence they came from."""
    narrow = " | ".join(cut(140, i) for i in range(4))     # 4 cuts
    wide = cut(400, 9)
    assert len(narrow) > len(wide), (len(narrow), len(wide))
    assert clip.clause_truncated(narrow, 140), "and every clause is a cut"
    assert clip.clause_truncated(wide, 400)
    # Severity gets it right where length does not.
    assert clip.prefer(
        clip.clip_signature([" | ".join(cut(140, i + j * 4) for i in range(4))
                             for j in range(20)]),
        clip.clip_signature([cut(400, j) for j in range(20)])) > 0


def test_an_unclipped_corpus_beats_any_clipped_one():
    whole = clip.clip_signature([clean(i) for i in range(30)])
    for width in (140, 200, 480):
        cutup = clip.clip_signature([cut(width, i) for i in range(20)])
        assert clip.prefer(whole, cutup) < 0, width


def test_too_few_beats_clipped_but_never_beats_clean():
    """"Not measurable" is a weaker claim against a corpus than "measured and
    cut" — but it is not evidence of being clean either."""
    few = clip.clip_signature(["one short excerpt"])
    cutup = clip.clip_signature([cut(140, i) for i in range(20)])
    whole = clip.clip_signature([clean(i) for i in range(30)])
    assert few["verdict"] == "TOO_FEW"
    assert clip.prefer(few, cutup) < 0
    assert clip.prefer(few, whole) > 0


def test_equal_corpora_give_no_preference():
    a = clip.clip_signature([cut(140, i) for i in range(20)])
    assert clip.prefer(a, a) == 0


def test_the_signature_is_the_same_for_a_generator_and_a_list():
    """The worker's census passes a generator. The first version consumed it
    in the clause loop and then counted an exhausted iterator, reporting
    "excerpts_scanned: 0" beside "total_clauses: 1386" — a denominator of zero
    attached to a finding about 1,121 clipped clauses."""
    rows = [cut(140, i) for i in range(20)]
    assert clip.clip_signature(iter(rows)) == clip.clip_signature(rows)
    assert clip.clip_signature(iter(rows))["excerpts_scanned"] == 20


# ── the research ledger reads its own column ──────────────────────────

def _research_wb(tmp_path, headers, rows, tab="Evidence_Detail"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = tab
    ws.append(list(headers))
    for r in rows:
        ws.append(list(r))
    path = tmp_path / "research.xlsx"
    wb.save(path)
    return str(path)


#: T. Rowe's real header row, verbatim.
TROW_HEADERS = ("Evidence_ID", "Fact_ID", "SubCap_IDs", "Claim", "Direction",
                "DQ_Facet", "ERS_Core", "ERS_Total", "Tier", "Recency",
                "Excerpt", "Anchor_Quote", "Source_Name", "URL")


def _trow_row(i, excerpt, anchor=None):
    return [f"E-{i:03d}", f"E-{i:03d}:F1", "P2C1.5.1", "FACT", "supports",
            "works", "4.2", "3.4", "T1", "CURRENT", excerpt, anchor,
            "Vibe Prospecting", "https://example.com"]


def test_the_plain_excerpt_column_is_read(tmp_path):
    """The whole first defect in one test: this shape produced 0 excerpts out
    of 1,642 and said nothing about it."""
    path = _research_wb(tmp_path, TROW_HEADERS,
                        [_trow_row(i, clean(i)) for i in range(14)])
    obs = []
    out = parse_research_workbook(path, obs)
    got = [r for r in out["ledger"] if r.get("excerpt")]
    assert len(got) == 14, [o.kind for o in obs]
    assert got[0]["excerpt"] == clean(0)


def test_an_anchor_quote_is_read_when_the_excerpt_column_is_blank(tmp_path):
    path = _research_wb(tmp_path, TROW_HEADERS,
                        [_trow_row(i, None, clean(i)) for i in range(14)])
    out = parse_research_workbook(path, [])
    assert [r["excerpt"] for r in out["ledger"]] == [clean(i)
                                                     for i in range(14)]


def test_the_unclipped_column_wins_within_a_row(tmp_path):
    """MEM-0162: on one package the Excerpt column held the assessor's
    paraphrase and only Anchor_Quote was verbatim. A fixed alias order gets
    that wrong half the time, so the row picks by condition."""
    path = _research_wb(tmp_path, TROW_HEADERS,
                        [_trow_row(i, cut(140, i), clean(i))
                         for i in range(14)])
    out = parse_research_workbook(path, [])
    assert [r["excerpt"] for r in out["ledger"]] == [clean(i)
                                                     for i in range(14)]


def test_a_generation_with_no_excerpt_column_still_parses(tmp_path):
    """The fill-from-detail-tabs generation must not regress: no excerpt
    column is thin, not broken."""
    headers = [h for h in TROW_HEADERS if h not in ("Excerpt", "Anchor_Quote")]
    rows = [[c for h, c in zip(TROW_HEADERS, _trow_row(i, None))
             if h not in ("Excerpt", "Anchor_Quote")] for i in range(14)]
    out = parse_research_workbook(_research_wb(tmp_path, headers, rows), [])
    assert len(out["ledger"]) == 14
    assert all(r.get("excerpt") is None for r in out["ledger"])


def test_the_ledger_read_no_longer_hardcodes_none():
    import inspect

    from dma_worker import workbook_parser
    src = inspect.getsource(workbook_parser.parse_research_workbook)
    assert '"excerpt": None,       # filled from the detail tabs below' \
        not in src, "the flat None is back and 1,642 values go unread again"
    assert '"excerpt": _best_excerpt(' in src


# ── persist chooses by severity, and says so ──────────────────────────

def test_persist_decides_once_over_the_corpus_not_per_row():
    """A single string cannot reveal the width it was cut at, so the choice
    has to be made over the whole corpus before the row loop."""
    import inspect

    from dma_worker import persist
    src = inspect.getsource(persist)
    assert "excerpt_clip.prefer(led_sig, res_sig)" in src
    assert src.index("led_sig = excerpt_clip.clip_signature") < \
        src.index('for ev in (evidence or []):'), \
        "the comparison must precede the row loop it governs"


def test_persist_observes_the_choice_when_either_corpus_is_clipped():
    import inspect

    from dma_worker import persist
    src = inspect.getsource(persist)
    assert "excerpt_source_chosen_by_clip_severity" in src
    assert "Length is the wrong criterion" in src, \
        "the observation must carry the reason, not just the outcome"


def test_the_preferred_source_still_fills_in_for_the_other():
    """A preference is not a reason to serve an empty drawer."""
    import inspect

    from dma_worker import persist
    src = inspect.getsource(persist)
    assert 'if r.get("excerpt") and (research_wins or not ev.get("excerpt")):' \
        in src


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
