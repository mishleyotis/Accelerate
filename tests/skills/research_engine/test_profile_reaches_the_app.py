"""The Client Research Profile is one of two client-facing reports, and until
2026-08-30 the app never read it.

WHY THIS EXISTS. `_RPT_DECOYS` carried "profile", so `_classify_artefact`
returned None for every .docx whose name contained it — and the engine's own
filename for this report is `Client_Profile_Research_<entity>_<date>.docx`.
All eight of its sections reached no table, while four page packs named
"Client Profile DOCX" as their source of truth for firmographics, the
leadership roster, focus-area verbatim quotes and the financial series. The
producer fetched them out of Drive by hand because the app held none of them.

The sharpest part: the OTHER classifier in the same service already
recognised the artefact — `classification.ARTEFACT_REGISTRY` matches it as
`client_profile` priority 3 and the scanner writes that into
`import_files.classified_kind`. Classified, recorded, then dropped: the
AUD-0091 shape this codebase names by number.

These walk the artefact from the engine's renderer to the rows the app would
store, over the REAL rendered document rather than a fixture of one.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from engine import narrative as N
from engine import report_spec as RS
from engine import reports as R

from .fixtures import bank_evidence, new_run, sign_off_sections
from .test_report_structure import _rec

sys.path.insert(0, "/home/user/Accelerate/apps/worker")


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    """The real Client Research Profile, rendered by the engine."""
    tmp = tmp_path_factory.mktemp("profile")
    run = new_run(tmp, n=6)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    spec = RS.SPECS["client_research"]
    for sec in spec.sections:
        if sec.kind in RS.CARD_KINDS:
            for i in range(RS.INSIGHT_CARD_MIN):
                N.write(wb, spec.key, sec.id, _rec(sec.id, eids),
                        actor="report-research-producer", card=f"IC-{i + 1}")
        else:
            N.write(wb, spec.key, sec.id, _rec(sec.id, eids),
                    actor="report-research-producer")
    sign_off_sections(wb)
    out = R.render(wb, spec, tmp / "out", force=False)
    return Path(out["path"] if isinstance(out, dict) else out)


def test_the_rendered_filename_is_the_one_the_app_classifies(rendered):
    """The spec's filename and the classifier's pattern are one artefact seen
    from two ends; they disagreed for the whole of the profile's life."""
    import job_main as J
    from dma_worker import classification

    class F:
        def __init__(self, name):
            self.name = name
            self.path_segments = ["Acme Credit Union - DMA"]

    assert J._classify_artefact(F(rendered.name)) == ("profile", 0), (
        f"{rendered.name} is not classified as its own artefact")
    got = classification.classify(rendered.name)
    assert got is not None and got.kind == "client_profile", got


#: The kind each of the profile's eight sections resolves to. Written down
#: because "it parsed" is not the property that matters — a section stored
#: under a kind nobody can ask for by name is as unreachable as one that
#: never landed, which is exactly what `unmapped:*` was.
EXPECTED_KINDS = {
    "1": "entity_and_scope",
    "2": "search_scope",
    "3": "evidence_sources",
    "4": "capability_picture",
    "5": "insight_cards",
    "6": "technology_utilisation",
    "7": "findings",
    "8": "artefact_index",
}


def test_every_section_of_the_profile_resolves_to_a_nameable_kind(rendered):
    """The parser emits a row per Heading2 — the blocks — and the SECTION's
    identity rides in `section_kind`, resolved from its Heading1. Six of the
    eight resolved to `unmapped:*` before the profile's own patterns existed.
    """
    from dma_worker.report_parser import parse_report

    obs: list = []
    sections = parse_report(str(rendered), obs)
    assert sections, f"the parser read nothing. observations: {obs}"
    kinds = {s.section_kind for s in sections}
    unmapped = sorted(k for k in kinds if k.startswith("unmapped:"))
    assert not unmapped, (
        f"these sections resolve to a kind no consumer can ask for: "
        f"{unmapped}")
    assert kinds == set(EXPECTED_KINDS.values()), sorted(kinds)


def test_adding_the_profiles_kinds_did_not_move_the_assessment_reports(
        rendered):
    """The profile's patterns are LAST, after every assessment-report
    pattern, so nothing here can change how that report is kinded — the
    AUD-0039 defect was a section silently stored under the wrong kind, and
    a wrongly-kinded section reads as a correctly-kinded one to every
    consumer."""
    from dma_worker.report_parser import _TITLE_RES, section_kind_for

    for n, heading, want in ((1, "Executive summary", "executive_summary"),
                             (3, "Maturity by pillar", "assessment_results"),
                             (6, "Peer position", "benchmark_comparison"),
                             (7, "Recommendations", "recommendations"),
                             (4, "Evidence and its limits",
                              "evidence_sources"),
                             (5, "Findings", "findings"),
                             (2, "Method, scope and limits", "methodology"),
                             (8, "What would change this assessment",
                              "data_gaps_confidence")):
        kind, basis = section_kind_for(n, heading)
        assert (kind, basis) == (want, "heading"), (heading, kind, basis)
    assert _TITLE_RES, "the table must not be empty"


def test_the_declared_blocks_arrive_as_their_own_rows(rendered):
    """`Section.blocks` become real Heading2s, which is the grain
    `document_sections` wants — and the grain `embed.py` scopes on."""
    from dma_worker.report_parser import parse_report

    headings = {s.heading for s in parse_report(str(rendered), [])}
    pillar_sec = RS.SPECS["client_research"].section("4")
    for block in pillar_sec.blocks:
        assert block in headings, (block, sorted(headings)[:12])


def test_the_two_reports_kinds_do_not_collide_once_namespaced(rendered):
    """Both reports produce `evidence_sources`, and both produce a
    findings-shaped section. Un-namespaced, one key would carry two
    documents' answers with no way to tell which said what."""
    import job_main as J
    from dma_worker.report_parser import parse_report

    kinds = {s.section_kind for s in parse_report(str(rendered), [])}
    assert "evidence_sources" in kinds or "findings" in kinds, (
        f"expected a colliding kind to exist before namespacing: {kinds}")

    namespaced = {f"{J.PROFILE_KIND_PREFIX}{k}" for k in kinds}
    assert not (namespaced & kinds), "the prefix must actually separate them"
    assert all(k.startswith("client_research:") for k in namespaced)


def test_a_section_can_name_the_document_it_came_from(rendered):
    """`persist_package` attributed every section to ONE report_artefact_id,
    which was right while only one report was ingested and a provenance hole
    the moment two were — `get_report_bundle` does not project artefact_id at
    all, so a consumer could not tell them apart even in principle."""
    from dma_worker.report_parser import ReportSection, parse_report

    sec = parse_report(str(rendered), [])[0]
    assert hasattr(sec, "artefact_id") and sec.artefact_id is None
    sec.artefact_id = "file-123"
    assert ReportSection("k", None, "h", "b").artefact_id is None


def test_the_profile_is_requeued_with_the_rest_of_its_package():
    """A requeue blanks the checksums of the package's artefacts so the next
    scan retries them. A profile left out of that set would never be
    reconsidered after a failed ingest."""
    import inspect

    import job_main as J

    src = inspect.getsource(J._requeue)
    assert '"profile"' in src, src


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
