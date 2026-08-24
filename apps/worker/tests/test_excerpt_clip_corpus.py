"""A clipped corpus is named at the tier it arrives in, and at any width.

MEM-0129 and MEM-0143, both BLOCKER, both `worker`. Package-origin evidence
arrived with every clause cut at exactly 140 characters and joined with
" | ". Three of those total 426 and pass the 50-500 verbatim window without a
murmur, so nothing fired — and 1,960 of 2,063 served evidence items across
583 of 595 cells showed a client a quotation cut mid-word.

MEM-0143 recorded the shape of the FIRST repair as its own defect: it covered
only the ids one surface cited and left the 752-record corpus the heatmap
cites untouched. The same shape nearly recurred here. Guarding
`register_evidence` closes the door a producer walks through; PACKAGE-ORIGIN
EVIDENCE NEVER GOES THROUGH THAT DOOR — it arrives in this parser. So the
rule lives in `packages/shared/excerpt_clip.py` and is enforced at both ends.

The corpus half of the rule works the width out for itself. `_RATIONALE_KEYS`
in the parser already carries a `rationale_150_chars` spelling, so a second
clip width is a column name in the shipped corpus, not a hypothetical.
"""
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.workbook_parser import (            # noqa: E402
    _best_excerpt, _pick_all, parse_evidence_master,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[3] /
                       "packages" / "shared"))
from excerpt_clip import (                          # noqa: E402
    CLAUSE_CLIP_WIDTH, CLIP_SHARE, MIN_CLAUSES, MIN_CLIP_WIDTH,
    clause_truncated, clip_signature,
)

W = CLAUSE_CLIP_WIDTH


def cut(width: int = W, seed: str = "a") -> str:
    """A clause of exactly `width` characters ending mid-word."""
    body = (f"the {seed} vendor deployed a platform across every region and "
            f"the filing describes it in detail ") * 6
    out = body[:width - 6] + "Salesf"
    assert len(out) == width and out[-1].isalnum()
    return out


def whole(n: int = 90, seed: str = "a") -> str:
    """Ordinary prose of a length that varies with the seed."""
    body = (f"The {seed} bank published a statement describing the migration "
            f"of its core platform in under four months. ") * 4
    return body[:n].rstrip() + "."


# ── the corpus check finds the width rather than being told it ────────

def test_the_measured_signature_is_reported_as_clipped():
    scan = clip_signature([" | ".join([cut(), cut(), cut()])] * 8)
    assert scan["verdict"] == "CLIPPED"
    assert scan["width"] == W
    assert scan["clipped"] == 24 and scan["total_clauses"] == 24


@pytest.mark.parametrize("width", [140, 150, 200, 120, 61])
def test_a_clip_at_any_width_is_found_without_being_told_it(width):
    """The hole in the first pass at this fix, closed. A rule that knows only
    140 walks straight past a package clipped at 150 — and the parser's own
    `rationale_150_chars` alias says that package exists."""
    scan = clip_signature([" | ".join([cut(width), cut(width)])] * 8)
    assert scan["verdict"] == "CLIPPED"
    assert scan["width"] == width


def test_the_verdict_carries_the_arithmetic_that_produced_it():
    """Invariant 12's discipline, applied to an observation: a reader must be
    able to check the claim without re-running the scan."""
    scan = clip_signature([" | ".join([cut(), cut(), cut()])] * 8)
    assert f"{scan['clipped']} of {scan['total_clauses']}" in scan["reason"]
    assert f"exactly {W} characters" in scan["reason"]
    assert scan["share"] == 1.0
    assert "Salesf" in scan["example_ends"]


def test_the_runner_up_length_is_stated_so_the_spike_can_be_judged():
    """The measured corpus was 4,461 at 140 against 23 at the next length.
    A spike is only a spike relative to something."""
    corpus = [" | ".join([cut(), cut(), whole(70, "b")])] * 8
    scan = clip_signature(corpus)
    assert scan["verdict"] == "CLIPPED"
    assert scan["runner_up"] < scan["clipped"]


# ── and does not cry wolf on prose ────────────────────────────────────

def test_ordinary_prose_of_varying_lengths_is_clean():
    corpus = [" | ".join([whole(n, chr(97 + n % 26)), whole(n + 7, "z")])
              for n in range(60, 120)]
    scan = clip_signature(corpus)
    assert scan["verdict"] == "CLEAN", scan["reason"]


def test_real_excerpts_from_the_corpus_are_clean():
    scan = clip_signature([
        "The bank published a statement on 2 August 2021 describing the "
        "conversion of the acquired platform in under four months.",
        "FINRA BrokerCheck records three customer arbitration awards against "
        "the firm across its entire operating history.",
        "Rated 4.3 over 4,262 ratings on the Android store, a lifetime "
        "average on the channel that carries the whole relationship.",
        "NCUA call report Q4 2025 states total assets of $8.9bn against "
        "shares of $7.4bn and loans of $6.1bn.",
        "The 2026 proxy names three committees with technology oversight in "
        "their charters and no standalone technology committee.",
        "A job posting dated 14 March 2026 seeks a Snowflake platform "
        "engineer reporting to the head of data.",
    ] * 3)
    assert scan["verdict"] == "CLEAN", scan["reason"]


def test_short_repeated_clauses_are_not_a_clip():
    """A ticker, a quarter, a role legitimately collide at one length. Below
    MIN_CLIP_WIDTH that is prose, not a cut."""
    short = "x" * (MIN_CLIP_WIDTH - 1)
    scan = clip_signature([" | ".join([short] * 3)] * 20)
    assert scan["verdict"] == "CLEAN"


def test_a_clause_at_the_width_that_ends_cleanly_is_not_a_cut():
    """The rule is a CUT, not a WIDTH — a sentence that happens to run to
    the clip width and ends at a boundary is ordinary prose."""
    clean = cut()[:-1] + "."
    scan = clip_signature([" | ".join([clean] * 3)] * 8)
    assert scan["verdict"] == "CLEAN"


# ── "I could not look" is never reported as "I found nothing" ──────────

def test_a_corpus_too_small_to_judge_says_so_rather_than_clean():
    scan = clip_signature([whole(90)] * 3)
    assert scan["verdict"] == "TOO_FEW"
    assert scan["width"] is None
    assert "NOT a finding of clean" in scan["reason"]
    assert str(MIN_CLAUSES) in scan["reason"]


def test_an_empty_corpus_is_too_few_and_not_clean():
    assert clip_signature([])["verdict"] == "TOO_FEW"
    assert clip_signature(None)["verdict"] == "TOO_FEW"


def test_every_verdict_states_its_denominator():
    for corpus in ([], [whole(90)] * 3, [whole(n) for n in range(60, 120)],
                   [" | ".join([cut()] * 3)] * 8):
        scan = clip_signature(corpus)
        assert "total_clauses" in scan and "excerpts_scanned" in scan
        assert scan["verdict"] in ("CLIPPED", "CLEAN", "TOO_FEW")
        assert scan["reason"]


def test_a_clean_verdict_names_what_it_measured():
    """A check that ran and found nothing must show its working, or the next
    reader cannot tell it from a check that was skipped."""
    scan = clip_signature([whole(n, chr(97 + n % 26)) for n in range(60, 120)])
    assert scan["verdict"] == "CLEAN"
    assert f"{CLIP_SHARE:.0%}" in scan["reason"] or "no clause ends" in scan["reason"]


# ── the two halves of the rule agree ──────────────────────────────────

def test_the_single_excerpt_check_and_the_corpus_check_are_one_rule():
    excerpt = " | ".join([cut(), cut(), cut()])
    assert clause_truncated(excerpt) is not None
    assert clip_signature([excerpt] * 8)["verdict"] == "CLIPPED"


def test_three_clipped_clauses_still_pass_the_length_window():
    """The reason both checks exist: 3 x 140 joined by ' | ' is 426
    characters, comfortably inside 50-500."""
    excerpt = " | ".join([cut(), cut(), cut()])
    assert 50 <= len(excerpt) <= 500


# ── the worker names it, at the tier the corpus arrives in ────────────

def _ledger(tmp_path, rows, headers=("Evidence_ID", "Source", "URL", "Tier",
                                     "Claim_Type", "Excerpt")):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Evidence_Master"
    ws.append(list(headers))
    for r in rows:
        ws.append(list(r))
    path = tmp_path / "ev.xlsx"
    wb.save(path)
    return str(path)


def _obs(obs, kind):
    return [o for o in obs if o.kind == kind]


def test_a_clipped_ledger_is_named_at_parse(tmp_path):
    rows = [[f"E-{i:03d}", "Scan", "https://x", "T1", "FACT",
             " | ".join([cut(seed=str(i)), cut(seed=str(i) + "b")])]
            for i in range(8)]
    obs = []
    out = parse_evidence_master(_ledger(tmp_path, rows), obs)
    assert len(out) == 8
    hit = _obs(obs, "evidence_excerpts_clause_truncated")
    assert len(hit) == 1, "a clipped ledger must produce exactly one verdict"
    d = hit[0].detail
    assert d["width"] == W and d["clipped"] == 16
    assert "9 product names" in d["consequence"]
    assert "re-ingest" in d["fix"]


def test_a_clean_ledger_produces_no_verdict(tmp_path):
    rows = [[f"E-{i:03d}", "Report", "https://x", "T2", "FACT",
             whole(60 + i * 3, chr(97 + i))] for i in range(14)]
    obs = []
    parse_evidence_master(_ledger(tmp_path, rows), obs)
    assert _obs(obs, "evidence_excerpts_clause_truncated") == []


def test_the_length_window_would_have_passed_every_one_of_those_rows(tmp_path):
    """The control that makes the check worth having: this ledger is entirely
    inside 50-500 and entirely cut."""
    rows = [[f"E-{i:03d}", "Scan", "https://x", "T1", "FACT",
             " | ".join([cut(seed=str(i)), cut(seed=str(i) + "b")])]
            for i in range(8)]
    obs = []
    out = parse_evidence_master(_ledger(tmp_path, rows), obs)
    assert all(50 <= len(r["excerpt"]) <= 500 for r in out)
    assert _obs(obs, "evidence_excerpts_clause_truncated")


def test_the_clipped_rows_are_still_read_rather_than_dropped(tmp_path):
    """REPORTED, NOT RAISED. Refusing would take down every run whose only
    evidence is clipped — most of the measured corpus. An evidence drawer
    that ships empty tells a client less than one that ships a cut; what the
    vetter needs is to KNOW."""
    rows = [[f"E-{i:03d}", "Scan", "https://x", "T1", "FACT",
             " | ".join([cut(seed=str(i))] * 3)] for i in range(8)]
    obs = []
    out = parse_evidence_master(_ledger(tmp_path, rows), obs)
    assert [r["e_id"] for r in out] == [f"E-{i:03d}" for i in range(8)]
    assert all(r["excerpt"] for r in out)


# ── two columns claim to hold the excerpt; the whole one wins ─────────

def test_both_excerpt_columns_are_resolved_not_just_the_first():
    assert _pick_all({"excerpt": 5, "anchor_quote": 9, "tier": 2},
                     ("excerpt", "anchor_quote", "verbatim")) == [5, 9]


def test_the_unclipped_column_wins_whichever_order_it_sits_in():
    """MEM-0162 measured this on richwood-bank: the Excerpt column held the
    assessor's paraphrase and only Anchor_Quote was verbatim. A fixed alias
    order gets that wrong half the time, so the row picks by CONDITION."""
    assert _best_excerpt([cut(), whole(90)]) == whole(90)
    assert _best_excerpt([whole(90), cut()]) == whole(90)


def test_when_every_candidate_is_clipped_the_first_is_kept():
    assert _best_excerpt([cut(seed="a"), cut(seed="b")]) == cut(seed="a")


def test_an_empty_or_numeric_cell_is_not_an_excerpt():
    assert _best_excerpt([None, "", "   "]) is None
    assert _best_excerpt(["12345", whole(90)]) == whole(90)
    assert _best_excerpt(["12345"]) is None


def test_a_row_carrying_both_columns_lands_the_verbatim_one(tmp_path):
    """End to end through the parser, on the two-column shape one package in
    the intake tree actually ships: 899 facts with both a paraphrase and an
    anchor quote, and not one pair identical."""
    headers = ("Evidence_ID", "Source", "URL", "Tier", "Claim_Type",
               "Excerpt", "Anchor_Quote")
    rows = [[f"E-{i:03d}", "Filing", "https://x", "T1", "FACT",
             cut(seed=str(i)), whole(90 + i, chr(97 + i))] for i in range(8)]
    obs = []
    out = parse_evidence_master(_ledger(tmp_path, rows, headers), obs)
    assert [r["excerpt"] for r in out] == [whole(90 + i, chr(97 + i))
                                           for i in range(8)]
    assert _obs(obs, "evidence_excerpts_clause_truncated") == [], \
        "the clipped column was not the one kept, so nothing was clipped"


# ── the rule is held in ONE place ─────────────────────────────────────

def test_the_connector_and_the_worker_read_the_same_module():
    """MEM-0193's defect class is RULE_HELD_IN_TWO_PLACES_DRIFTS, and this
    rule drifted while it was being written."""
    import inspect

    from dma_worker import workbook_parser
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "mcp"))
    from dma_mcp import register

    assert register.CLAUSE_CLIP_WIDTH is CLAUSE_CLIP_WIDTH
    assert register._clause_truncated is clause_truncated
    src = inspect.getsource(workbook_parser)
    assert "excerpt_clip.clip_signature" in src
    assert "140" not in src.split("_shared_roots")[0], \
        "the worker must not restate the width it imports"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
