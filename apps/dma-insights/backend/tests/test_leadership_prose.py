"""Labelled-prose leadership recovery (derive_leadership).

Many Client-Profile / Assessment reports render "4.3 Leadership Overview" as
prose — "<Role Title>: <Full Name> — <desc> [E-ID]" (Zions, OneAZ, BOK …) — which
the table/JSON extractors miss, leaving the panel empty OR (when the ingest
grabbed a colon-title fragment) showing junk like "CEO: Brandon". These pin the
prose recovery: a role-keyword title + a person-guarded name, never a fabricated
leader; and the entity-dir resolver that lets the sweep reach a sibling version
subdir without crossing into another entity.
"""
from __future__ import annotations

import os

import docx

from app.scripts.derive_leadership import _entity_dir, _prose_leadership


def _write_doc(path: str, lines: list[str]) -> None:
    d = docx.Document()
    for ln in lines:
        d.add_paragraph(ln)
    d.save(path)


def test_prose_leadership_extracts_role_colon_name(tmp_path) -> None:
    root = tmp_path / "Acme Bank - DMA"
    rep = root / "04_reports"
    rep.mkdir(parents=True)
    _write_doc(str(rep / "DMA_Client_Profile_Report.docx"), [
        "4.3 Leadership Overview",
        "CEO: Brandon Michaels — leads strategic vision incl. Backbase [E-001]",
        "Chief Information & Operations Officer: Jennifer Smith (10-yr BaNCS lead)",
        "VP CISO: Monique M. — dedicated security governance [E-143]",
        # NOT leaders — gap statement + a non-role colon line + a product phrase:
        "Leadership Gaps: No identified gaps — CDO, CTO, CISO all filled.",
        "Address: 123 Main Street, Phoenix Arizona",
        "Platform: Data Cloud, Salesforce FSC",
        "4.4 Acquisition History",
    ])
    out = _prose_leadership(str(root))
    names = {r["name"] for r in out}
    assert names == {"Brandon Michaels", "Jennifer Smith", "Monique M"}
    # title carried, role-bearing.
    by = {r["name"]: r["title"] for r in out}
    assert by["Brandon Michaels"] == "CEO"
    assert "Officer" in by["Jennifer Smith"]


def test_prose_leadership_honest_empty_when_no_named_roster(tmp_path) -> None:
    root = tmp_path / "Empty Bank - DMA"
    rep = root / "04_reports"
    rep.mkdir(parents=True)
    _write_doc(str(rep / "Client_Profile_Report.docx"), [
        "4.3 Leadership Overview",
        "Leadership Gaps: No identified gaps — all roles filled.",
        "4.4 Acquisition History",
    ])
    assert _prose_leadership(str(root)) == []


def test_prose_reaches_sibling_version_subdir(tmp_path) -> None:
    # Real Zions layout: canonical root is the "FINAL" subdir, the leadership
    # prose lives in a sibling "v2.0" subdir under the same entity package dir.
    batch = tmp_path / "batch_01"
    entity = batch / "Zions Bancorporation - DMA"
    final = entity / "Zions_DMA FINAL" / "04_reports"
    v2 = entity / "Zions DMA v2.0"
    final.mkdir(parents=True)
    v2.mkdir(parents=True)
    _write_doc(str(final / "Assessment_Report.docx"), ["No leadership here."])
    _write_doc(str(v2 / "Zions_DMA_Report.docx"), [
        "4.3 Leadership Overview",
        "Chief Technology Officer: Margaret Mayor (ex-Discover, Capital One)",
    ])
    # the entity dir is the child of batch_01 — sweeping it reaches the sibling.
    assert _entity_dir(str(final)) == str(entity)
    out = _prose_leadership(str(final))
    assert [r["name"] for r in out] == ["Margaret Mayor"]


def test_entity_dir_no_cross_entity_leak(tmp_path) -> None:
    # A non-nested package: the entity dir IS the root (child of the batch dir),
    # so the sweep never climbs into a sibling entity.
    batch = tmp_path / "batch_10"
    a = batch / "OneAZ Credit Union - DMA"
    b = batch / "Other Bank - DMA"
    (a / "04_reports").mkdir(parents=True)
    (b / "04_reports").mkdir(parents=True)
    assert _entity_dir(str(a)) == str(a)
    _write_doc(str(a / "04_reports" / "Profile_Report.docx"),
               ["CEO: Brandon Michaels — vision [E-1]"])
    _write_doc(str(b / "04_reports" / "Profile_Report.docx"),
               ["CEO: Someone Else — other entity [E-2]"])
    out = _prose_leadership(str(a))
    assert [r["name"] for r in out] == ["Brandon Michaels"]
    assert not os.path.exists(str(a / "Other Bank - DMA"))
