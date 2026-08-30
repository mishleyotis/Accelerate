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
    CLAUSE_CLIP_WIDTH, CLAUSE_SPLIT, MIN_CLAUSES, MIN_CLIPPED,
    MIN_CLIP_WIDTH, NEIGHBOUR_RATIO, clause_truncated,
    clip_signature,
)

W = CLAUSE_CLIP_WIDTH


def cut(width: int = W, seed: str = "a") -> str:
    """A DISTINCT clause of exactly `width` characters ending mid-word.

    Distinct matters. The first version of these fixtures repeated one string
    and the corpus check counted occurrences, so a single sentence stacked
    fifty clauses on one length and looked exactly like a clip. Production
    said otherwise: baxter serves 1,517 excerpt renderings drawn from 87
    distinct strings. Five separate sentences ending on the same integer is
    the evidence; the same sentence fifty times is one coincidence, not
    fifty.
    """
    body = (f"the {seed} vendor deployed a platform across every region and "
            f"the filing describes it in detail ") * 8
    out = body[:width - 6] + "Salesf"
    assert len(out) == width and out[-1].isalnum()
    return out


def clipped_corpus(width: int = W, n: int = 10) -> list:
    """`n` distinct excerpts, each two distinct clauses cut at `width`."""
    return [CLAUSE_SPLIT.join([cut(width, f"a{i}"), cut(width, f"b{i}")])
            for i in range(n)]


def whole(n: int = 90, seed: str = "a") -> str:
    """Ordinary prose of length `n`, ENDING ON A WHOLE WORD.

    Ending on a word character is what a natural clause does — the last
    character of the last word. That is why the width coincidence is the
    signal and the mid-word test is only corroboration, and it is why these
    fixtures must not end every clause with a full stop: a corpus that did
    would pass the check without ever exercising it.
    """
    body = (f"The {seed} bank published a statement describing the migration "
            f"of its core platform in under four months and named the "
            f"vendors involved ") * 4
    out = body[:n]
    while out and not out[-1].isalnum():
        out = out[:-1] + "x"
    assert len(out) == n
    return out


def spread(lo: int = 60, hi: int = 140, skip: int | None = None) -> list:
    """A corpus whose clause lengths spread the way prose does.

    `skip` leaves one length free, so a fixture that plants a clip at that
    width is measuring only what it planted.
    """
    return [whole(n, chr(97 + n % 26)) for n in range(lo, hi) if n != skip]


# ── the corpus check finds the width rather than being told it ────────

def test_the_measured_signature_is_reported_as_clipped():
    scan = clip_signature(clipped_corpus())
    assert scan["verdict"] == "CLIPPED"
    assert scan["width"] == W
    assert scan["clipped"] == 20 and scan["distinct_clauses"] == 20


@pytest.mark.parametrize("width", [140, 150, 200, 120, 61])
def test_a_clip_at_any_width_is_found_without_being_told_it(width):
    """The hole in the first pass at this fix, closed. A rule that knows only
    140 walks straight past a package clipped at 150 — and the parser's own
    `rationale_150_chars` alias says that package exists."""
    scan = clip_signature(clipped_corpus(width))
    assert scan["verdict"] == "CLIPPED"
    assert scan["width"] == width


def test_the_verdict_carries_the_arithmetic_that_produced_it():
    """Invariant 12's discipline, applied to an observation: a reader must be
    able to check the claim without re-running the scan."""
    scan = clip_signature(clipped_corpus())
    assert f"{scan['clipped']} DISTINCT" in scan["reason"]
    assert f"exactly {W} characters" in scan["reason"]
    assert f"against {scan['neighbours']} distinct" in scan["reason"]
    assert "Salesf" in scan["example_ends"]


def test_the_spike_is_measured_against_its_neighbours_not_the_corpus():
    """A clip does not have to be most of a corpus — production proved that.
    Here the clipped rows are a minority and the spike is still a spike."""
    scan = clip_signature(clipped_corpus(n=6) + spread())
    assert scan["verdict"] == "CLIPPED" and scan["width"] == W
    assert scan["clipped"] < scan["distinct_clauses"] / 4, \
        "the clipped clauses are well under a quarter of the corpus"
    assert scan["ratio"] >= NEIGHBOUR_RATIO


def test_the_verdict_separates_distinct_clauses_from_renderings():
    """87 distinct strings serving 1,517 renderings is the shape production
    has. Both numbers matter and they are not the same number."""
    corpus = clipped_corpus() * 5
    scan = clip_signature(corpus)
    assert scan["distinct_clauses"] == 20
    assert scan["total_clauses"] == 100
    assert scan["clipped"] == 20 and scan["clipped_served"] == 100


# ── and does not cry wolf on prose ────────────────────────────────────

def test_ordinary_prose_of_varying_lengths_is_clean():
    scan = clip_signature([CLAUSE_SPLIT.join([whole(n, chr(97 + n % 26)),
                                              whole(n + 7, "z")])
                           for n in range(60, 120)])
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


def test_one_sentence_repeated_is_one_coincidence_not_fifty():
    """The defect that counting OCCURRENCES produced. A corpus that reuses
    one excerpt across many cells is thin, not clipped, and calling it
    clipped would put a false BLOCKER on an honest package."""
    scan = clip_signature([cut()] * 50)
    assert scan["verdict"] == "CLEAN", scan["reason"]
    assert scan["distinct_clauses"] == 1 and scan["total_clauses"] == 50


def test_short_repeated_clauses_are_not_a_clip():
    """A ticker, a quarter, a role legitimately collide at one length. Below
    MIN_CLIP_WIDTH that is prose, not a cut."""
    scan = clip_signature([CLAUSE_SPLIT.join(
        ["x" * (MIN_CLIP_WIDTH - 1) + str(i) for i in range(3)])
        for i in range(20)])
    assert scan["verdict"] == "CLEAN"


def test_a_clause_at_the_width_that_ends_cleanly_is_not_a_cut():
    """The rule is a CUT, not a WIDTH — a sentence that happens to run to
    the clip width and ends at a boundary is ordinary prose."""
    scan = clip_signature([cut(seed=f"s{i}")[:-1] + "." for i in range(20)])
    assert scan["verdict"] == "CLEAN"


def test_a_handful_of_distinct_clauses_at_one_length_is_below_the_floor():
    scan = clip_signature(clipped_corpus(n=2) + spread())
    assert scan["verdict"] == "CLEAN"
    assert str(MIN_CLIPPED) in scan["reason"]


# ── the case production found that the first rule missed ──────────────

BAXTER_80 = [
    "Active LinkedIn postings: Sr Salesforce Software Engineer (Vernon "
    "Hills), Sr Clo",
    "BCU selected Glia for digital member service: messaging, video "
    "banking, voice, C",
    "Casual dress code, flexible work arrangements, inclusive culture "
    "supporting work",
    "Department distribution: Finance 13%, Customer Service 12%, "
    "Operations 5%, Sales",
    "Banking Tech Awards USA 2025 finalist: Best Digital Initiative by "
    "Community Bank",
    "Brett Craig: former EVP & CIO of Target (Fortune 50), led global "
    "tech/digital/da",
    "Trustpilot reviews (25 reviews): complaints about false fraud flags "
    "on legitimat",
    "BCU member intelligence team deployed 2016: 2 analysts + 1 data tech "
    "manager. On",
    "BCU ranked #1 in proactive guidance among all Tethr users; excelled "
    "in action-fo",
    "Bhavna Guglani (BCU CDO): digital channels are primary growth "
    "engines; branch-ce",
]


def test_the_baxter_clip_at_eighty_is_found():
    """Verbatim from production, 2026-08-24, the promoted baxter heatmap.

    THE FIRST RULE CALLED THIS CLEAN and it was serving a client quotations
    ending "Sr Clo", "branch-ce" and "voice, C". It covered 12 of 87 distinct
    clauses — 14% — so a share threshold could not see it, while the whole
    rest of that histogram is 67 lengths holding one or two clauses each and
    80 holding fourteen. That is what fixed the rule: a spike is measured
    against its NEIGHBOURS, never against the corpus."""
    assert all(len(c) == 80 and c[-1].isalnum() for c in BAXTER_80)
    scan = clip_signature(BAXTER_80 + spread(skip=80))
    assert scan["verdict"] == "CLIPPED"
    assert scan["width"] == 80
    assert scan["clipped"] == len(BAXTER_80)
    assert scan["ratio"] >= NEIGHBOUR_RATIO


def test_the_baxter_clip_survives_the_repetition_it_ships_with():
    """Those 12 render 173 times across the page. Deduplicating must not
    lose the clip, only stop the repetition from inventing one."""
    scan = clip_signature(BAXTER_80 * 15 + spread(skip=80))
    assert scan["verdict"] == "CLIPPED" and scan["width"] == 80
    assert scan["clipped"] == 10 and scan["clipped_served"] == 150


def test_a_minority_clip_would_have_passed_a_share_rule():
    """The control that says why the rule changed rather than the threshold."""
    corpus = BAXTER_80 + spread(skip=80)
    scan = clip_signature(corpus)
    assert scan["clipped"] / scan["distinct_clauses"] < 0.25
    assert scan["verdict"] == "CLIPPED"


# ── "I could not look" is never reported as "I found nothing" ──────────

def test_a_corpus_too_small_to_judge_says_so_rather_than_clean():
    scan = clip_signature([whole(90, str(i)) for i in range(3)])
    assert scan["verdict"] == "TOO_FEW"
    assert scan["width"] is None
    assert "NOT a finding of clean" in scan["reason"]
    assert str(MIN_CLAUSES) in scan["reason"]


def test_an_empty_corpus_is_too_few_and_not_clean():
    assert clip_signature([])["verdict"] == "TOO_FEW"
    assert clip_signature(None)["verdict"] == "TOO_FEW"


def test_every_verdict_states_its_denominators():
    for corpus in ([], [whole(90, str(i)) for i in range(3)], spread(),
                   clipped_corpus()):
        scan = clip_signature(corpus)
        assert {"total_clauses", "distinct_clauses",
                "excerpts_scanned"} <= set(scan)
        assert scan["verdict"] in ("CLIPPED", "CLEAN", "TOO_FEW")
        assert scan["reason"]


def test_a_clean_verdict_names_what_it_measured():
    """A check that ran and found nothing must show its working, or the next
    reader cannot tell it from a check that was skipped."""
    scan = clip_signature(spread())
    assert scan["verdict"] == "CLEAN"
    assert "distinct" in scan["reason"]


# ── the two halves of the rule agree ──────────────────────────────────

def test_the_single_excerpt_check_and_the_corpus_check_are_one_rule():
    corpus = clipped_corpus()
    assert all(clause_truncated(e) for e in corpus)
    assert clip_signature(corpus)["verdict"] == "CLIPPED"


def test_the_single_check_finds_baxters_clip_only_when_told_the_width():
    """Which is exactly why the corpus check exists. The door check is told
    140 and cannot know 80; the corpus check works 80 out for itself."""
    assert all(clause_truncated(c) is None for c in BAXTER_80)
    assert all(clause_truncated(c, 80) for c in BAXTER_80)
    assert clip_signature(BAXTER_80 + spread(skip=80))["width"] == 80


def test_three_clipped_clauses_still_pass_the_length_window():
    """The reason both checks exist: 3 x 140 joined by ' | ' is 426
    characters, comfortably inside 50-500."""
    excerpt = CLAUSE_SPLIT.join([cut(seed="a"), cut(seed="b"), cut(seed="c")])
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
