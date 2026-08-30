"""A re-uploaded workbook is the same assessment, not a second one.

The ingest guard resolves an unchanged package to the run it already produced
instead of minting another. It used to require the DRIVE FILE ID to match as
well as the checksum — and re-uploading a workbook (delete, upload again, which
is what people do) mints a new file id for the same bytes. The guard could not
match, and a byte-identical assessment ingested as a second run.

Measured in production 2026-08-16: 286 pending runs across 171 entities, 105
carrying more than one. One entity holds three runs at run_seq 1, 2 and 3 with
the same request id, the same composite (1.63), the same 120 scored cells and
the same completed_at. The same scan reported "130 artefact(s) seen before and
absent now" — the replaced-file signature.

The unchanged-tree path was never broken and is asserted here too: a scan over
an untouched tree creates nothing, which the production scan confirmed the same
day (8,208 files, new=0 changed=0, 0 ingested).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "worker"))

SRC = (ROOT / "apps" / "worker" / "dma_worker" / "persist.py").read_text()


def _guard() -> str:
    """The idempotence SELECT, as source."""
    i = SRC.index("if artefact_id and artefact_checksum and not remint:")
    return SRC[i:SRC.index("prior = cur.fetchone()", i)]


def test_the_guard_matches_on_content_not_on_the_drive_file_id():
    g = _guard()
    assert "source_checksum = %s" in g, "content is what identifies the run"
    assert "source_artefact_id = %s" not in g, (
        "the guard requires the Drive file id to match, so a re-uploaded "
        "workbook — new file id, identical bytes — mints a duplicate run")


def test_the_guard_is_still_scoped_to_the_entity():
    """Checksum alone would collide across clients if two packages ever
    carried identical bytes. The pair is the key."""
    assert "entity_id = %s" in _guard()


def test_a_deliberate_remint_still_bypasses_it():
    """FORCE_FOLDER after a parser fix must still mint: the tree is unchanged
    and the extraction is not."""
    assert "not remint" in _guard()


def test_it_takes_the_LATEST_run_when_several_already_exist():
    """105 entities already carry duplicates. Resolving to run_seq 1 would
    hand back the oldest ingest of the same bytes; the newest is the one a
    later pass produced."""
    g = _guard()
    assert re.search(r"ORDER BY run_seq DESC\s+LIMIT 1", g), g


def test_the_unchanged_tree_path_is_untouched():
    """The diff still decides which folders are even considered; this guard is
    the second line, for a package whose FILES changed identity but whose
    CONTENT did not."""
    from dma_worker.scan_diff import FileStat, diff_tree
    prior = {"f1": "abc", "f2": "def"}
    cur = [FileStat("f1", ("a",), "w.xlsx", "abc", 1),
           FileStat("f2", ("b",), "w.xlsx", "def", 1)]
    d = diff_tree(cur, prior)
    assert not d.new and not d.changed and len(d.unchanged) == 2


def test_a_replaced_file_reads_as_new_AND_missing():
    """Why the second line is needed at all: a re-upload is not 'changed', it
    is a new id plus a missing one, so the diff correctly routes it to ingest
    and only the content guard can tell it is the same assessment."""
    from dma_worker.scan_diff import FileStat, diff_tree
    d = diff_tree([FileStat("f2", ("a",), "w.xlsx", "abc", 1)], {"f1": "abc"})
    assert [f.file_id for f in d.new] == ["f2"]
    assert d.missing == ["f1"]
    assert not d.changed
