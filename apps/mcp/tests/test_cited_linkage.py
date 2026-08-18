"""ET-07 — a cited source resolves to the cells it supports.

ET-04 asks whether the chip opens onto a quotation. This asks the question
a reader asks immediately afterwards: which capability does this support?

Measured on a promoted run: 178 served evidence rows, 72 of them carrying
no cell link at all, 28 of those cited by a section. The row a user
actually clicked — a Great Place To Work profile behind an employee
sentiment tile — answered "no cell links served for this item". That is
why an unlinked citation is worse than no citation: an uncited sentence
asks nothing of the reader, and a citation invites them to drill in and
then hands them an orphan.

The honest exception is real. A charter registry entry, an NCUA
call-report period file or a board roster is evidence about the
INSTITUTION rather than about a capability, and inventing a cell for it
would be the misattribution failure this gate exists to reduce. So it
passes STATED — by the grain of the section citing it, or by a rung the
producer wrote naming the id — and never by being forced into a false
link.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import _check_cited_linkage  # noqa: E402


def _row(e_id, cells=()):
    return {"e_id": e_id, "stored_id": e_id, "excerpt": "x" * 80,
            "linked_subcap_ids": list(cells)}


def test_the_measured_case_an_unlinked_row_behind_a_sentiment_tile():
    payload = {"context_sentiment": {"context_tiles": [
        {"audience": "employee", "rows": [{"source": "Great Place To Work",
                                           "rating": 88, "e_id": "E-CC-049"}],
         "e_ids": ["E-CC-049"]}], "e_ids": ["E-CC-049"]}}
    out = _check_cited_linkage("context", payload, [_row("E-CC-049")],
                               {"E-CC-049": "context_sentiment"})
    assert len(out) == 1
    r = out[0]
    assert r["gate_id"] == "ET-07" and r["severity"] == "block"
    assert r["section"] == "context_sentiment"
    assert "E-CC-049" in r["message"]
    assert "no cell links served for this item" in r["message"]


def test_a_row_carrying_one_cell_link_passes():
    out = _check_cited_linkage(
        "context", {"timeline": {"e_ids": ["E-CC-004"]}},
        [_row("E-CC-004", ["P4C3.1.1"])], {"E-CC-004": "timeline"})
    assert out == []


def test_a_registry_entry_cited_by_regulatory_standing_passes_by_grain():
    """The honest exception, class one: a section that does not reason at
    cell grain. A charter number and a licence type are facts about the
    institution, and a capability cell for them would be invented."""
    out = _check_cited_linkage(
        "context", {"regulatory_standing": {"primary_regulator": "NCUA",
                                            "e_ids": ["E-CC-006"]}},
        [_row("E-CC-006")], {"E-CC-006": "regulatory_standing"})
    assert out == []


def test_the_same_registry_row_cited_by_a_cell_grain_section_does_not_pass():
    """The exemption belongs to the SECTION's grain, not to the source. The
    same row cited by the timeline is a claim about the capability history,
    and it owes the reader a cell."""
    out = _check_cited_linkage(
        "context", {"timeline": {"e_ids": ["E-CC-006"]}},
        [_row("E-CC-006")], {"E-CC-006": "timeline"})
    assert len(out) == 1 and out[0]["section"] == "timeline"


def test_a_stated_rung_naming_the_id_passes():
    """The honest exception, class two: the producer says why it links to
    none, in prose the section serves whole, so the reader gets the reason
    rather than a silent gap."""
    payload = {"context_sentiment": {
        "e_ids": ["E-CC-053"],
        "r_layer": {"verdict": "kept", "probes_run": [
            "E-CC-053 is the CFPB complaint database's own hit count for "
            "this entity — a corpus-level measure of the register, linked "
            "to no capability cell because it measures the register."]}}}
    assert _check_cited_linkage("context", payload, [_row("E-CC-053")],
                                {"E-CC-053": "context_sentiment"}) == []


def test_an_empty_state_ladder_naming_the_id_states_it_too():
    payload = {"context_sentiment": {
        "e_ids": ["E-CC-052"],
        "empty_state": {"reason": "no rated employee line",
                        "sources_searched": [
                            "BBB — E-CC-052 carries a letter grade, which "
                            "has no scale and no sample and so supports no "
                            "capability cell"]}}}
    assert _check_cited_linkage("context", payload, [_row("E-CC-052")],
                                {"E-CC-052": "context_sentiment"}) == []


def test_a_rung_that_names_a_different_id_does_not_excuse_this_one():
    """A general sentence about linkage is not a statement about this
    source — otherwise the exception is a switch, and one boilerplate
    paragraph excuses every orphan on the page."""
    payload = {"context_sentiment": {
        "e_ids": ["E-CC-049", "E-CC-052"],
        "r_layer": {"probes_run": ["E-CC-052 is a bureau letter grade and "
                                   "supports no cell"]}}}
    out = _check_cited_linkage("context", payload,
                               [_row("E-CC-049"), _row("E-CC-052")],
                               {"E-CC-049": "context_sentiment",
                                "E-CC-052": "context_sentiment"})
    assert [r["message"].split()[0] for r in out] == ["E-CC-049"]


def test_the_financial_series_carries_period_files_and_is_exempt():
    """Five NCUA call-report period files support the trajectory card and
    no capability cell. Forcing them onto one would be a false link on the
    best-evidenced rows in the run."""
    payload = {"financial_series": {"points": [], "e_ids": ["E-CC-041"]}}
    assert _check_cited_linkage("overview", payload, [_row("E-CC-041")],
                                {"E-CC-041": "financial_series"}) == []


class _Conn:
    """Stands in for `resolve_evidence_id()` (0046) plus the link table.

    The resolution rule itself is a SQL function and is tested against the
    real database in apps/api/tests/test_evidence_supersession.py — including
    the case where a successor carries no links and must NOT capture the
    citation. What this double exercises is what ET-07 does with the answer.
    """

    def __init__(self, links, superseded=None):
        self.links = links
        self.superseded = superseded or {}      # e_id -> successor

    def cursor(self):
        conn = self

        class _Cur:
            def execute(self, sql, params=None):
                cited = params[0]
                # the function's own rule: forward only onto a successor that
                # carries links, otherwise stay put
                succ = conn.superseded.get(cited)
                resolved = succ if succ and conn.links.get(succ) else cited
                n = len(conn.links.get(resolved, ()))
                self.row = (resolved, n) if resolved != cited and n else None

            def fetchone(self):
                return self.row
        return _Cur()


def test_a_superseded_citation_discloses_and_does_not_refuse():
    """The reader is not stranded: the serve path resolves through the same
    0046 pointer, so the chip opens on the successor with its links and its
    fuller excerpt. Blocking would refuse a citation that renders correctly —
    and would refuse it on 4,366 ids at once, every bare row whose links 0043
    moved."""
    payload = {"cell_evidence": {"e_ids": ["E-BCU-012"]}}
    conn = _Conn({"E-BCU-012-R2": ["P4C1.1.%d" % i for i in range(5)]},
                 superseded={"E-BCU-012": "E-BCU-012-R2"})
    out = _check_cited_linkage("heatmap", payload, [_row("E-BCU-012")],
                               {"E-BCU-012": "cell_evidence"}, conn)
    assert len(out) == 1
    assert out[0]["gate_id"] == "ET-07"
    assert out[0]["severity"] == "warn", "a resolvable citation must not block"
    msg = out[0]["message"]
    assert "superseded by E-BCU-012-R2" in msg and "5 cells" in msg
    assert "no cell links served for this item" not in msg


def test_a_genuine_orphan_still_blocks():
    """The negative control on the disclosure. If every unlinked citation
    became a warning, ET-07 would stop doing the job it was built for — a
    reader invited to drill in and handed nothing."""
    payload = {"cell_evidence": {"e_ids": ["E-BCU-016"]}}
    out = _check_cited_linkage("heatmap", payload, [_row("E-BCU-016")],
                               {"E-BCU-016": "cell_evidence"}, _Conn({}))
    assert len(out) == 1
    assert out[0]["severity"] == "block"
    assert "no cell links served for this item" in out[0]["message"]


def test_a_successor_that_carries_no_links_does_not_rescue_the_citation():
    """Supersession alone is not resolution. Moving a citation onto a
    successor that links nothing would trade one orphan for another while
    making the gate report it repaired."""
    payload = {"cell_evidence": {"e_ids": ["E-BCU-009"]}}
    conn = _Conn({}, superseded={"E-BCU-009": "E-BCU-009-R2"})
    out = _check_cited_linkage("heatmap", payload, [_row("E-BCU-009")],
                               {"E-BCU-009": "cell_evidence"}, conn)
    assert len(out) == 1
    assert out[0]["severity"] == "block"


def test_a_suffixed_id_whose_original_is_also_unlinked_is_a_plain_orphan():
    payload = {"cell_evidence": {"e_ids": ["E-BCU-016-R2"]}}
    out = _check_cited_linkage("heatmap", payload, [_row("E-BCU-016-R2")],
                               {"E-BCU-016-R2": "cell_evidence"},
                               _Conn({"E-BCU-016": []}))
    assert len(out) == 1
    assert out[0]["severity"] == "block"
    assert "no cell links served for this item" in out[0]["message"]


def test_without_a_connection_the_check_still_runs():
    """The sibling lookup is an improvement to the message, never a
    precondition for the verdict."""
    out = _check_cited_linkage("heatmap", {"cell_evidence": {}},
                               [_row("E-BCU-016-R2")],
                               {"E-BCU-016-R2": "cell_evidence"})
    assert len(out) == 1 and out[0]["gate_id"] == "ET-07"


def test_the_exemption_is_per_page_not_per_section_name():
    """`firmographics` is identity grain on the overview. A section that
    happened to share the name on another page would not inherit the
    exemption — the registry is keyed by (page, section)."""
    payload = {"firmographics": {"e_ids": ["E-CC-006"]}}
    assert _check_cited_linkage("overview", payload, [_row("E-CC-006")],
                                {"E-CC-006": "firmographics"}) == []
    assert len(_check_cited_linkage("context", payload, [_row("E-CC-006")],
                                    {"E-CC-006": "firmographics"})) == 1
