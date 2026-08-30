"""The report tier and the technographic scan — the two holes the 2026-08-30
coverage audit found, and the contracts that now close them.

The audit measured sixteen report sections with NO OWNER and an ERS column
computed by nothing. Both were invisible because the Golden 1 run stopped
before the report stage, so "the pipeline works" and "the pipeline cannot
produce a report" were true at the same time.

These pin the four things the review actually asked about a report section —
how the argument is weighed, how an absence is confirmed against proxies,
how assumptions and bias are noted, how inference is tagged and confirmed —
plus the accuracy measure, the independence of the verdict, and the scan's
machine copy against the app's own parser.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
ENGINE = REPO / "plugins/dma-insights/skills/dma-research"
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(REPO / "apps" / "worker"))

from engine import ers as ERS                      # noqa: E402
from engine import narrative as N                  # noqa: E402
from engine import report_spec as RS               # noqa: E402
from engine import techscan                        # noqa: E402
from fixtures import bank_evidence, new_run        # noqa: E402


def _section(**over) -> dict:
    """A section that passes every check, so each test can break exactly one."""
    rec = {
        # The blocks are §1's declared anatomy, and the writer refuses a body
        # without them: they become real Heading2s in the .docx, which is the
        # grain the app parses and scopes its vectors at.
        "Body": (
            "## Who this is\n"
            "Acme Credit Union is a state-chartered, federally insured credit "
            "union assessed under the CU sub-vertical in PUBLIC evidence "
            "mode. Its digital banking platform went live in the third "
            "quarter of 2024 and member adoption is reported at 47 percent "
            "within ninety days of launch.\n\n"
            "## What was in scope\n"
            "The scope of this profile is the "
            "retail estate the call report describes. No public evidence "
            "names a documented cadence for reviewing the digital strategy "
            "itself. [INF] That silence more likely reflects the disclosure "
            "habits of a member-owned institution than an absence of "
            "internal practice, and it is carried forward as an open "
            "question rather than as a finding.\n\n"
            "## What was out of scope, and what that bounds\n"
            "Every claim here rests on a "
            "source a reader can reopen, and the ceiling on each is set by "
            "what a public-evidence engagement can reach rather than by what "
            "the institution does internally. The profile is written to be "
            "argued with rather than believed, and every figure in it can be "
            "traced to the excerpt that carries it rather than to any "
            "recollection of having read one somewhere in the record."),
        "Evidence_IDs": "",          # filled by the caller
        "Weighing": (
            "The adoption reading was weighed against the possibility that a "
            "launch figure flatters a platform in its first quarter; the "
            "ninety-day restatement was preferred because it is the later "
            "of the two and the more conservative. The alternative reading, "
            "that adoption reflects forced migration rather than uptake, was "
            "rejected because no migration deadline appears in any source."),
        "Absence_Basis": (
            "Direct disclosure, delay-and-criticism proxy and the NCUA "
            "regulatory rung were all searched on 2026-08-29; the published "
            "board roster names members only and no regulator has posted a "
            "governance report addressing digital oversight."),
        "Assumptions": (
            "Assumed the 2024 platform decision is still in force, which "
            "cuts in favour of the maturity reading; a reversal would lower "
            "the ceiling rather than raise it."),
        "Bias_Notes": (
            "A public-evidence run over-reads what an institution publishes "
            "and under-reads what it does not. This client issues press "
            "releases readily, so its intent is better evidenced than its "
            "delivery, and this section is correspondingly stronger on the "
            "former."),
        "Inference_Tags": (
            "[INF] the cadence silence reflects disclosure habit rather than "
            "absent practice — would be confirmed by requesting the "
            "strategic-planning calendar in discovery"),
    }
    rec.update(over)
    return rec


def _for_section(rec: dict, report: str, section: str) -> dict:
    """The same record, wearing another section's declared block anatomy.

    `narrative.write` refuses a body that does not carry its section's
    blocks in order, so a test that moves to a different section has to
    move its subheadings too. The prose is deliberately unchanged: these
    tests are about the refusals, not about the writing.
    """
    from engine import report_spec as RS
    sec = RS.SPECS[report].section(section)
    rec = dict(rec)
    prose = [ln for ln in rec["Body"].splitlines()
             if ln.strip() and not ln.strip().startswith("##")]
    if not sec.blocks:
        rec["Body"] = "\n".join(prose)
        return rec
    per = max(1, len(prose) // len(sec.blocks))
    out, i = [], 0
    for n, block in enumerate(sec.blocks):
        out.append(f"## {block}")
        chunk = prose[i:i + per] if n < len(sec.blocks) - 1 else prose[i:]
        out.extend(chunk or ["Nothing further is recorded for this block."])
        out.append("")
        i += per
    rec["Body"] = "\n".join(out).strip()
    return rec

def _ready_run(tmp_path):
    run = new_run(tmp_path, n=6)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0], n=3)
    return run, wb, eids


# ── the section is an argument, or it is refused ─────────────────────────

def test_a_written_section_records_its_whole_argument(tmp_path):
    _, wb, eids = _ready_run(tmp_path)
    out = N.write(wb, "client_research", "1",
                  _section(Evidence_IDs=", ".join(eids)),
                  actor="report-research-producer")
    row = N.rows_for(wb, "client_research")["1"]
    for field in ("Weighing", "Absence_Basis", "Assumptions", "Bias_Notes",
                  "Inference_Tags", "Accuracy_Basis"):
        assert str(row[field]).strip(), f"{field} did not reach the workbook"
    assert out["inferences"] == 1 and out["absence_claimed"] is True
    # the verdict is somebody else's, and starts empty
    assert not str(row["Review_Verdict"]).strip()


def test_a_weighing_with_only_one_side_is_refused(tmp_path):
    _, wb, eids = _ready_run(tmp_path)
    with pytest.raises(N.NarrativeRefusal, match="nothing on the other side"):
        N.write(wb, "client_research", "1", _section(
            Evidence_IDs=", ".join(eids),
            Weighing=("The evidence shows the platform went live in 2024 and "
                      "adoption reached 47 percent, which supports the "
                      "reading that the institution executes what it says it "
                      "will do across its retail estate.")),
            actor="report-research-producer")


def test_an_asserted_absence_needs_its_proxy_ladder(tmp_path):
    _, wb, eids = _ready_run(tmp_path)
    with pytest.raises(N.NarrativeRefusal, match="statement about the search"):
        N.write(wb, "client_research", "1",
                _section(Evidence_IDs=", ".join(eids), Absence_Basis=""),
                actor="report-research-producer")


def test_an_untagged_inference_is_refused(tmp_path):
    """A body that marks an inference and does not enumerate it is an
    inference travelling as a fact."""
    _, wb, eids = _ready_run(tmp_path)
    with pytest.raises(N.NarrativeRefusal, match="travelling as a fact"):
        N.write(wb, "client_research", "1",
                _section(Evidence_IDs=", ".join(eids), Inference_Tags=""),
                actor="report-research-producer")


def test_an_inference_tag_must_say_what_would_confirm_it(tmp_path):
    _, wb, eids = _ready_run(tmp_path)
    with pytest.raises(N.NarrativeRefusal, match="guess with a label"):
        N.write(wb, "client_research", "1", _section(
            Evidence_IDs=", ".join(eids),
            Inference_Tags="[INF] the silence reflects disclosure habit"),
            actor="report-research-producer")


def test_unnamed_assumptions_and_bias_are_refused(tmp_path):
    _, wb, eids = _ready_run(tmp_path)
    for field in ("Assumptions", "Bias_Notes"):
        with pytest.raises(N.NarrativeRefusal, match=field):
            N.write(wb, "client_research", "1",
                    _section(Evidence_IDs=", ".join(eids), **{field: ""}),
                    actor="report-research-producer")


def test_a_section_that_cites_nothing_is_refused(tmp_path):
    """§3 'Evidence base' is about the client, and requires_citation is True."""
    _, wb, _ = _ready_run(tmp_path)
    with pytest.raises(N.NarrativeRefusal, match="hallucination"):
        N.write(wb, "client_research", "3",
                _for_section(_section(Evidence_IDs=""), "client_research", "3"),
                actor="report-research-producer")


def test_a_section_the_spec_exempts_may_ship_uncited(tmp_path):
    """`requires_citation=False` was honoured by the RENDERER and ignored by
    the WRITER, which refused an empty Evidence_IDs on all sixteen sections.
    §1 describes the run, not the client — there is nothing about the client
    for it to cite, and a spec field only half the pipeline reads is a
    contradiction rather than a safeguard."""
    _, wb, _ = _ready_run(tmp_path)
    assert RS.SPECS["client_research"].section("1").requires_citation is False
    out = N.write(wb, "client_research", "1", _section(Evidence_IDs=""),
                  actor="report-research-producer")
    assert out["section"] == "1"


def test_an_unresolvable_citation_is_refused(tmp_path):
    _, wb, eids = _ready_run(tmp_path)
    with pytest.raises(N.NarrativeRefusal, match="fail-closed"):
        N.write(wb, "client_research", "1",
                _section(Evidence_IDs=", ".join(eids) + ", E-999"),
                actor="report-research-producer")


# ── accuracy is measured, never asserted ─────────────────────────────────

def test_accuracy_is_computed_from_the_workbook(tmp_path):
    _, wb, eids = _ready_run(tmp_path)
    out = N.write(wb, "client_research", "1",
                  _section(Evidence_IDs=", ".join(eids)),
                  actor="report-research-producer")
    acc = out["accuracy"]
    assert acc["cited_ids"] == len(eids) == acc["resolved_ids"]
    assert acc["unresolved_ids"] == []
    assert acc["ers_mass"] > 0, "ERS mass must be real, not zero"
    assert acc["citation_density_per_100w"] > 0
    basis = str(N.rows_for(wb, "client_research")["1"]["Accuracy_Basis"])
    assert "ERS mass" in basis and "citation" in basis


# ── the verdict belongs to somebody else ─────────────────────────────────

def test_a_section_author_cannot_review_their_own_section(tmp_path):
    _, wb, eids = _ready_run(tmp_path)
    N.write(wb, "client_research", "1", _section(Evidence_IDs=", ".join(eids)),
            actor="report-research-producer")
    with pytest.raises(N.NarrativeRefusal, match="not a review"):
        N.review(wb, "client_research", "1", verdict="PASS",
                 actor="report-research-producer",
                 dimensions={d: "PASS" for d in N.REVIEW_DIMENSIONS},
                 note="x" * 100)


def test_a_pass_that_contradicts_its_dimensions_is_refused(tmp_path):
    _, wb, eids = _ready_run(tmp_path)
    N.write(wb, "client_research", "1", _section(Evidence_IDs=", ".join(eids)),
            actor="report-research-producer")
    dims = {d: "PASS" for d in N.REVIEW_DIMENSIONS}
    dims["absence_rigour"] = "FAIL"
    with pytest.raises(N.NarrativeRefusal, match="contradicts its own"):
        N.review(wb, "client_research", "1", verdict="PASS",
                 actor="report-validator", dimensions=dims, note="x" * 100)


def test_every_review_dimension_is_required_by_name(tmp_path):
    _, wb, eids = _ready_run(tmp_path)
    N.write(wb, "client_research", "1", _section(Evidence_IDs=", ".join(eids)),
            actor="report-research-producer")
    dims = {d: "PASS" for d in N.REVIEW_DIMENSIONS if d != "bias_disclosure"}
    with pytest.raises(N.NarrativeRefusal, match="bias_disclosure"):
        N.review(wb, "client_research", "1", verdict="PASS",
                 actor="report-validator", dimensions=dims, note="x" * 100)


def test_a_rubber_stamp_note_is_refused(tmp_path):
    _, wb, eids = _ready_run(tmp_path)
    N.write(wb, "client_research", "1", _section(Evidence_IDs=", ".join(eids)),
            actor="report-research-producer")
    with pytest.raises(N.NarrativeRefusal, match="rubber stamp"):
        N.review(wb, "client_research", "1", verdict="PASS",
                 actor="report-validator",
                 dimensions={d: "PASS" for d in N.REVIEW_DIMENSIONS},
                 note="fine")


def test_rewriting_a_section_clears_its_verdict(tmp_path):
    """What was reviewed no longer exists."""
    _, wb, eids = _ready_run(tmp_path)
    rec = _section(Evidence_IDs=", ".join(eids))
    N.write(wb, "client_research", "1", rec, actor="report-research-producer")
    N.review(wb, "client_research", "1", verdict="PASS",
             actor="report-validator",
             dimensions={d: "PASS" for d in N.REVIEW_DIMENSIONS},
             note="Opened both citations; the ladder has three rungs and a "
                  "date; the weighing names the rejected reading.")
    assert N.rows_for(wb, "client_research")["1"]["Review_Verdict"] == "PASS"
    N.write(wb, "client_research", "1", rec, actor="report-research-producer")
    assert not str(
        N.rows_for(wb, "client_research")["1"]["Review_Verdict"]).strip()


def test_the_report_is_not_ready_until_every_section_is_reviewed(tmp_path):
    _, wb, eids = _ready_run(tmp_path)
    N.write(wb, "client_research", "1", _section(Evidence_IDs=", ".join(eids)),
            actor="report-research-producer")
    st = N.state(wb, "client_research")
    assert st["reports"]["client_research"]["sections"][0]["status"] == \
        "UNREVIEWED"
    assert not st["ready"]
    with pytest.raises(N.NarrativeRefusal):
        N.require_ready(wb, "client_research")


def test_every_spec_section_has_a_state_row(tmp_path):
    """Adding a section to the spec must show up as work, not vanish."""
    _, wb, _ = _ready_run(tmp_path)
    st = N.state(wb)
    for key, spec in RS.SPECS.items():
        got = {s["section"] for s in st["reports"][key]["sections"]}
        assert got == {str(s.id) for s in spec.sections}


# ── ERS: the column that used to ship empty ──────────────────────────────

def test_banking_evidence_computes_its_ers(tmp_path):
    _, wb, eids = _ready_run(tmp_path)
    scores = [r["ERS"] for r in wb.rows("Evidence_Detail")
              if str(r.get("E_ID") or "").strip()]
    assert scores and all(isinstance(s, (int, float)) for s in scores), \
        "ERS shipped empty in every run before 2026-08-30; it is computed now"


def test_corroboration_counts_source_identities_not_rows(tmp_path):
    """Three pages of one annual report are one source — the same rule
    single_source_fact enforces on the floors gate."""
    _, wb, _ = _ready_run(tmp_path)
    rows = [{"E_ID": "E-1", "Source_URL": "https://acme.example/ar#1",
             "SubCap_IDs": "P1C1.1.1", "Tier": "T2", "Recency": "CURRENT",
             "Excerpt": "x" * 200},
            {"E_ID": "E-2", "Source_URL": "https://acme.example/ar#2",
             "SubCap_IDs": "P1C1.1.1", "Tier": "T2", "Recency": "CURRENT",
             "Excerpt": "x" * 200}]
    score, why = ERS.corroboration(rows[0], rows)
    assert score == 1.0 and "stands alone" in why
    rows.append({"E_ID": "E-3", "Source_URL": "https://ncua.example/cr",
                 "SubCap_IDs": "P1C1.1.1", "Tier": "T1", "Recency": "CURRENT",
                 "Excerpt": "y" * 200})
    score2, _ = ERS.corroboration(rows[0], rows)
    assert score2 > score, "a genuine second identity must raise the score"


def test_undated_evidence_is_not_scored_as_current(tmp_path):
    """Invariant 9: undated is UNVERIFIED, never current."""
    assert ERS.RECENCY_SCORE["UNVERIFIED"] < ERS.RECENCY_SCORE["DATED"]


def test_ers_says_when_specificity_fell_back(tmp_path):
    """A degraded term must announce itself rather than score as if it had
    the signal it lacks."""
    row = {"Excerpt": "The platform went live in 2024.", "Tier": "T2",
           "Recency": "DATED", "SubCap_IDs": ""}
    _, why = ERS.specificity(row, None)
    assert "no retrieval ranking" in why
    score, why2 = ERS.specificity(row, {"lists": 3, "bm25": 0.8})
    assert "retrieval" in why2 and score > 3


# ── the scan's machine copy is what the app reads ────────────────────────

def test_the_scan_json_matches_the_apps_own_parser(tmp_path):
    from dma_worker.workbook_parser import parse_technographic_scan
    # prelim=False: PRELIM records a technology baseline of its own, and this
    # test counts the rows it writes itself.
    run = new_run(tmp_path, n=6, prelim=False)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0], n=3)
    cell = wb.selected_subcaps()[0]
    techscan.record(wb, product="Alkami Digital Banking", vendor="Alkami",
                    layer="CUST", status="CONFIRMED",
                    method="public_document",
                    basis="named live in the 2025 annual report",
                    providers=["clay", "web"],
                    subcaps=[cell], evidence_ids=eids,
                    source_urls=["https://acme.example/ar25"])
    techscan.render(wb, run.deliverables)
    path = run.deliverables / techscan.JSON_NAME
    obs = []
    n = parse_technographic_scan(str(path), obs)
    assert n >= 1, "the app must count the detections this scan recorded"
    summary = [o for o in obs if o.kind == "technographic_scan_summary"]
    assert summary, [o.kind for o in obs]
    detail = summary[0].detail
    assert detail["by_status"].get("CONFIRMED") == "1"
    assert detail["by_layer"].get("CUST") == "1"
    # the layers nobody looked at must be NAMED, never implied clean
    assert set(detail["layers_never_looked_at"]) == {"OPS", "DATA", "INFRA"}


def test_a_docx_without_its_sidecar_is_recorded_as_incomplete(tmp_path):
    """The human copy arriving alone is a package defect, not a scan."""
    from dma_worker.workbook_parser import parse_technographic_scan
    p = tmp_path / "Technographic_Scan_acme_2026-08-30.docx"
    p.write_bytes(b"not really a docx")
    obs = []
    assert parse_technographic_scan(str(p), obs) == 0
    assert [o for o in obs if o.kind == "technographic_scan_docx_only"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
