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

# ── the first live run's three defects, pinned ────────────────────────────

def test_pull_descends_into_workbook_subfolders(monkeypatch, tmp_path):
    """Flat pull left both workbooks behind (2026-08-20): the scoring and
    research workbooks live in subfolders and the package cannot be vetted
    without them."""
    tree = {
        "root": [
            {"id": "readme", "name": "README.md", "mimeType": "text/markdown"},
            {"id": "scoring", "name": "03_scoring_workbook",
             "mimeType": drive_fetch.FOLDER_MIME},
        ],
        "scoring": [
            {"id": "wb", "name": "DMA_Scoring_Workbook_TROW.xlsx",
             "mimeType": "application/octet-stream"},
        ],
    }
    monkeypatch.setattr(drive_fetch, "_list_children",
                        lambda tok, fid: tree.get(fid, []))
    monkeypatch.setattr(
        drive_fetch, "_download",
        lambda tok, f, into: (into.mkdir(parents=True, exist_ok=True),
                              (into / f["name"]).write_bytes(b"x"),
                              f["name"])[-1])
    got = drive_fetch._pull_tree("tok", "root", tmp_path)
    assert got == 2
    assert (tmp_path / "03_scoring_workbook"
            / "DMA_Scoring_Workbook_TROW.xlsx").is_file()


def test_memory_file_is_found_under_a_variant_slug(monkeypatch):
    """A session pushed 't-rowe-price — synthesis memory.md'; the next
    session asks with the display_id. Identity decides, not spelling —
    otherwise the client ends up with two diverging memories."""
    rows = [{"id": "m1", "name": "t-rowe-price — synthesis memory.md",
             "mimeType": "text/markdown"},
            {"id": "x", "name": "README.md", "mimeType": "text/markdown"}]
    monkeypatch.setattr(drive_fetch, "_list_children", lambda tok, fid: rows)
    hit = drive_fetch._find_memory_file("tok", "fid", "t-rowe-price-group-inc")
    assert hit and hit["id"] == "m1"


def test_memory_lookup_never_crosses_clients(monkeypatch):
    rows = [{"id": "m1", "name": "houlihan-lokey — synthesis memory.md",
             "mimeType": "text/markdown"}]
    monkeypatch.setattr(drive_fetch, "_list_children", lambda tok, fid: rows)
    assert drive_fetch._find_memory_file(
        "tok", "fid", "t-rowe-price-group-inc") is None


def test_push_memory_heals_a_variant_name(monkeypatch, tmp_path):
    """When the found file's name differs from the canonical slug the push
    renames it — one client, one memory file, forever."""
    import io
    import json
    monkeypatch.setattr(drive_fetch, "MEMORY_DIR", tmp_path)
    (tmp_path / "t-rowe-price-group-inc.md").write_text("# memory")
    monkeypatch.setattr(drive_fetch, "_token", lambda: "tok")
    monkeypatch.setattr(drive_fetch, "_find_client_folder",
                        lambda tok, c: {"id": "fld", "name": "T. Rowe Price - DMA"})
    monkeypatch.setattr(drive_fetch, "_find_memory_file",
                        lambda tok, fid, c: {
                            "id": "m1",
                            "name": "t-rowe-price — synthesis memory.md"})
    calls = []

    class _Resp:
        def __enter__(self):
            return io.BytesIO(b"{}")

        def __exit__(self, *a):
            return False

    def fake_req(tok, url, data=None, method="GET", ctype=None):
        calls.append((method, url, data))
        return _Resp()

    monkeypatch.setattr(drive_fetch, "_req", fake_req)
    assert drive_fetch.push_memory("t-rowe-price-group-inc") == 0
    patches = [c for c in calls if c[0] == "PATCH"]
    assert len(patches) == 2  # content update + rename
    rename = json.loads(patches[1][2])
    assert rename["name"] == "t-rowe-price-group-inc — synthesis memory.md"


def test_push_bundle_creates_nested_folders_and_updates_in_place(monkeypatch, tmp_path):
    """The DMA Insights resume store: state.json + surfaces/<section>.json
    per client (owner, 2026-08-20) — created on first push, updated in
    place after, so a resuming workflow reads structure, not racing prose."""
    import json as _json
    bundle = tmp_path / "b.json"
    bundle.write_text('{"ok": true}')
    monkeypatch.setattr(drive_fetch, "_token", lambda: "tok")
    monkeypatch.setattr(drive_fetch, "_find_client_folder",
                        lambda tok, c: {"id": "root", "name": "X - DMA"})
    tree = {"root": [], "bundle-root": [], "surf": []}
    created = []

    def fake_list(tok, fid):
        return tree.get(fid, [])

    class _Resp:
        def __init__(self, payload):
            self._p = payload

        def __enter__(self):
            import io as _io
            return _io.BytesIO(_json.dumps(self._p).encode())

        def __exit__(self, *a):
            return False

    def fake_req(tok, url, data=None, method="GET", ctype=None):
        if method == "POST" and "uploadType" not in url:
            meta = _json.loads(data)
            fid = {"DMA Insights": "bundle-root",
                   "surfaces": "surf"}.get(meta["name"], "newf")
            created.append(meta["name"])
            tree.setdefault(meta["parents"][0], []).append(
                {"id": fid, "name": meta["name"],
                 "mimeType": drive_fetch.FOLDER_MIME})
            return _Resp({"id": fid})
        created.append(("upload", method, url.split("?")[0].rsplit("/", 1)[-1]))
        return _Resp({"id": "f1"})

    monkeypatch.setattr(drive_fetch, "_list_children", fake_list)
    monkeypatch.setattr(drive_fetch, "_req", fake_req)
    rc = drive_fetch.push_bundle("x", str(bundle),
                                 "surfaces/heatmap.workbook_scores.json")
    assert rc == 0
    assert "DMA Insights" in created and "surfaces" in created
    # second push: file now exists in 'surf' -> update via PATCH
    tree["surf"] = [{"id": "f1", "name": "heatmap.workbook_scores.json",
                     "mimeType": "application/json"}]
    created.clear()
    rc = drive_fetch.push_bundle("x", str(bundle),
                                 "surfaces/heatmap.workbook_scores.json")
    assert rc == 0
    assert any(c[1] == "PATCH" for c in created if isinstance(c, tuple))


def test_push_bundle_refuses_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    import pytest as _pytest
    with _pytest.raises(SystemExit) as e:
        drive_fetch.push_bundle("x", str(bad), None)
    assert "valid JSON" in str(e.value)
