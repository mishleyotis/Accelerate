"""Drive access by service account: the matching and naming logic, offline.

The network half is exercised live by the preflight itself (`drive_fetch.py
check` runs in STEP 0 of the synthesis routine and in this repo's own
verification); what tests pin here is the logic that must not drift — slug
matching that finds exactly one client folder or refuses loudly, and the
export mapping that keeps Google-native files downloadable.
"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import drive_fetch  # noqa: E402


def test_slug_normalises_client_names():
    assert drive_fetch._slug("T. Rowe Price Group, Inc.") == \
        "t-rowe-price-group-inc"
    assert drive_fetch._slug("Houlihan Lokey") == "houlihan-lokey"
    assert drive_fetch._slug("  Logix -- Federal  ") == "logix-federal"


def _with_children(monkeypatch, folders):
    rows = [{"id": f"id-{i}", "name": n,
             "mimeType": drive_fetch.FOLDER_MIME}
            for i, n in enumerate(folders)]
    monkeypatch.setattr(drive_fetch, "_list_children",
                        lambda tok, fid: rows)
    return rows


def test_exact_slug_match_wins(monkeypatch):
    rows = _with_children(monkeypatch, ["T. Rowe Price Group, Inc.",
                                        "Houlihan Lokey", "Thrivent"])
    hit = drive_fetch._find_client_folder("tok", "t-rowe-price-group-inc")
    assert hit["id"] == rows[0]["id"]


def test_partial_match_resolves_a_shorter_folder_name(monkeypatch):
    _with_children(monkeypatch, ["Houlihan Lokey", "Thrivent"])
    hit = drive_fetch._find_client_folder("tok", "houlihan-lokey-inc")
    assert hit["name"] == "Houlihan Lokey"


def test_no_match_names_what_is_visible(monkeypatch):
    _with_children(monkeypatch, ["Thrivent", "Bank of Utah"])
    with pytest.raises(SystemExit) as e:
        drive_fetch._find_client_folder("tok", "corporate-america")
    assert "Thrivent" in str(e.value) and "no client folder" in str(e.value)


def test_an_exact_match_beats_a_partial_sibling(monkeypatch):
    rows = _with_children(monkeypatch, ["Baxter Credit Union",
                                        "Baxter Credit Union (archive)"])
    hit = drive_fetch._find_client_folder("tok", "baxter-credit-union")
    assert hit["id"] == rows[0]["id"]


def test_ambiguous_partials_refuse_instead_of_guessing(monkeypatch):
    _with_children(monkeypatch, ["Baxter CU East", "Baxter CU West"])
    with pytest.raises(SystemExit) as e:
        drive_fetch._find_client_folder("tok", "baxter-cu")
    assert "multiple" in str(e.value)


def test_google_native_files_have_export_targets():
    for mime, (target, ext) in drive_fetch.EXPORTS.items():
        assert mime.startswith("application/vnd.google-apps.")
        assert ext.startswith(".")
        assert "google-apps" not in target


def test_the_one_precondition_is_named_in_the_module():
    """The share instruction must survive edits: it is the only manual step
    left anywhere in provisioning, and the preflight's failure text is where
    an operator learns it."""
    src = (HERE / "drive_fetch.py").read_text()
    assert drive_fetch.SA_EMAIL in src
    assert "Share" in src and "Editor" in src
