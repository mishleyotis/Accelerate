"""The workbook's locked peer set reaches the connector (SWBC gold audit
2026-10-04, RC-10(a)).

`Handoff_Lock` is where the research stage freezes the peer cohort
(`locked_peer_set`, 'A|B|C'; engine/workbook.py lock_peer_set). The worker
classified the tab as run config and read nothing from it, so a run whose
peers were IDENTIFIED but not SCORED — SWBC: Assurant, Fortegra, TruStage —
reached the connector with no peer set at all, and every peer gate read
"no peers". `parse_run_metadata` now carries the lock's keys into
run_manifest.payload.workbook_metadata, where dma_mcp/peer_set.py reads it.
"""
import openpyxl


def _book(tmp_path, lock_rows, meta_rows=()):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Run_Metadata"
    for k, v in meta_rows:
        ws.append([k, v])
    hl = wb.create_sheet("Handoff_Lock")
    hl.append(["Key", "Value"])
    for k, v in lock_rows:
        hl.append([k, v])
    path = tmp_path / "wb.xlsx"
    wb.save(path)
    return str(path)


def test_the_locked_peer_set_is_read(tmp_path):
    from dma_worker.workbook_parser import parse_run_metadata
    md = parse_run_metadata(_book(tmp_path, [
        ("locked_peer_set", "Assurant|Fortegra|TruStage"),
        ("peer_basis", "identified_not_scored"), ("peer_n", 3)]))
    assert md["locked_peer_set"] == "Assurant|Fortegra|TruStage"
    assert md["peer_basis"] == "identified_not_scored"
    assert md["peer_n"] == "3"


def test_run_metadata_still_wins_on_a_shared_key(tmp_path):
    from dma_worker.workbook_parser import parse_run_metadata
    md = parse_run_metadata(_book(tmp_path, [("peer_n", 3)],
                                  meta_rows=[("peer_n", "4")]))
    assert md["peer_n"] == "4"


def test_only_the_peer_keys_are_carried(tmp_path):
    """The lock also holds the catalogue hash and contract version; those
    are the engine's, not the app's."""
    from dma_worker.workbook_parser import parse_run_metadata
    md = parse_run_metadata(_book(tmp_path, [("catalogue_hash", "abc"),
                                             ("locked_peer_set", "Assurant")]))
    assert "catalogue_hash" not in md and md["locked_peer_set"] == "Assurant"


def test_the_tab_map_names_what_the_lock_feeds():
    from dma_worker.workbook_parser import _TAB_TARGET, _TAB_READERS
    feeds, confidence = _TAB_TARGET["Handoff_Lock"]
    assert confidence != "not_client_facing"
    assert "platform.platform_story" in feeds and "overview.scores" in feeds
    assert _TAB_READERS["Handoff_Lock"] == "parse_run_metadata"
