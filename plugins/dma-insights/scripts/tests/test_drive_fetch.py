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


def test_insights_taxonomy_name_derivation():
    """Owner, 2026-08-20: 'DMAI - <Client Name>' across all new clients."""
    assert drive_fetch._insights_name("T. Rowe Price - DMA") == \
        "DMAI - T. Rowe Price"
    assert drive_fetch._insights_name("Houlihan Lokey — DMA") == \
        "DMAI - Houlihan Lokey"
    assert drive_fetch._insights_name("Thrivent") == "DMAI - Thrivent"


def _bundle_rig(monkeypatch, tmp_path, tree, client_name="X - DMA"):
    import json as _json
    monkeypatch.setattr(drive_fetch, "_token", lambda: "tok")
    monkeypatch.setattr(drive_fetch, "BUNDLE_CACHE", tmp_path / "cache")
    monkeypatch.setattr(drive_fetch, "_find_client_folder",
                        lambda tok, c: {"id": "root", "name": client_name})
    created = []

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
            fid = {"DMAI - X": "bundle-root",
                   "surfaces": "surf"}.get(meta["name"], "newf")
            created.append(meta["name"])
            tree.setdefault(meta["parents"][0], []).append(
                {"id": fid, "name": meta["name"],
                 "mimeType": drive_fetch.FOLDER_MIME})
            return _Resp({"id": fid})
        if method == "PATCH" and "uploadType" not in url:
            created.append(("rename", _json.loads(data).get("name")))
            return _Resp({"id": "renamed"})
        created.append(("upload", method, url.split("?")[0].rsplit("/", 1)[-1]))
        return _Resp({"id": "f1"})

    monkeypatch.setattr(drive_fetch, "_list_children",
                        lambda tok, fid: tree.get(fid, []))
    monkeypatch.setattr(drive_fetch, "_req", fake_req)
    return created


def test_push_bundle_creates_taxonomy_folders_and_updates_in_place(monkeypatch, tmp_path):
    """The resume store under the owner taxonomy: DMAI - <Client>/state.json
    + surfaces/<section>.json — created on first push, updated in place
    after, so a resuming workflow reads structure, not racing prose."""
    bundle = tmp_path / "b.json"
    bundle.write_text('{"ok": true}')
    tree = {"root": [], "bundle-root": [], "surf": []}
    created = _bundle_rig(monkeypatch, tmp_path, tree)
    rc = drive_fetch.push_bundle("x", str(bundle),
                                 "surfaces/heatmap.workbook_scores.json")
    assert rc == 0
    assert "DMAI - X" in created and "surfaces" in created
    tree["surf"] = [{"id": "f1", "name": "heatmap.workbook_scores.json",
                     "mimeType": "application/json"}]
    created.clear()
    rc = drive_fetch.push_bundle("x", str(bundle),
                                 "surfaces/heatmap.workbook_scores.json")
    assert rc == 0
    assert any(c[1] == "PATCH" for c in created if isinstance(c, tuple))


def test_ensure_insights_heals_a_legacy_folder_name_and_captures_ids(monkeypatch, tmp_path):
    """A pre-taxonomy 'DMA Insights' folder is renamed, never duplicated,
    and the preflight lands folder_ids.json for every later push."""
    import json as _json
    tree = {"root": [{"id": "legacy", "name": "DMA Insights",
                      "mimeType": drive_fetch.FOLDER_MIME}],
            "legacy": []}
    created = _bundle_rig(monkeypatch, tmp_path, tree)
    rc = drive_fetch.ensure_insights("x")
    assert rc == 0
    assert ("rename", "DMAI - X") in created
    ids = _json.loads((tmp_path / "cache" / "x" /
                       "folder_ids.json").read_text())
    assert ids["insights_folder_id"] == "legacy"
    assert ids["insights_folder_name"] == "DMAI - X"
    assert ids["surfaces_folder_id"]


def test_push_bundle_writes_by_captured_id_without_a_folder_walk(monkeypatch, tmp_path):
    """After preflight the push must not depend on name resolution at all —
    resilience against renames and listing failures mid-session."""
    import json as _json
    cache = tmp_path / "cache" / "x"
    cache.mkdir(parents=True)
    (cache / "folder_ids.json").write_text(_json.dumps(
        {"insights_folder_id": "pinned-root",
         "insights_folder_name": "DMAI - X",
         "client_folder_name": "X - DMA"}))
    tree = {"pinned-root": [], "surf": []}
    created = _bundle_rig(monkeypatch, tmp_path, tree)

    def boom(tok, c):
        raise AssertionError("name resolution ran despite a captured id")
    monkeypatch.setattr(drive_fetch, "_find_client_folder", boom)
    bundle = tmp_path / "b.json"
    bundle.write_text('{"ok": true}')
    rc = drive_fetch.push_bundle("x", str(bundle), "state.json")
    assert rc == 0
    assert ("upload", "POST", "files") in created


def test_push_bundle_refuses_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    import pytest as _pytest
    with _pytest.raises(SystemExit) as e:
        drive_fetch.push_bundle("x", str(bad), None)
    assert "valid JSON" in str(e.value)


# ── the artefact taxonomy on Drive ───────────────────────────────────────
#
# artifact_store.py decides where an artefact belongs LOCALLY. These two
# subcommands carry that to Drive and back. What has to hold: the remote path
# is derived from the artefact's own name and never passed by a caller, the
# search is recursive so a misfiled artefact still prevents a redo, and asking
# whether work exists never creates the folder it asks about.

import artifact_store as _store  # noqa: E402


def _named(run="7a6ad71c-6225-4e0b-80fb-135cfd04b2dd", page="overview",
           section="hero", agent="overview-hero-producer", kind="payload",
           ts="20260821T050000Z"):
    return _store.artifact_name(run, page, section, agent, kind, ts)


def test_push_artifact_derives_the_remote_path_from_the_name(monkeypatch, tmp_path):
    """The destination is never passed. A caller that could name its own
    folder could file an overview payload under the heatmap, and the whole
    point of the naming scheme is that the file itself says where it goes."""
    name = _named()
    local = tmp_path / name
    local.write_text('{"run_id": "7a6ad71c-6225-4e0b-80fb-135cfd04b2dd", '
                     '"page": "overview", "section": "hero"}')
    tree = {"root": [], "bundle-root": []}
    created = _bundle_rig(monkeypatch, tmp_path, tree)
    assert drive_fetch.push_artifact("x", str(local)) == 0
    # The folders the taxonomy asks for, and no others.
    assert "10_overview" in created and "hero" in created
    assert "overview-hero-producer" in created


def test_push_artifact_refuses_a_file_that_is_not_named_by_the_store(tmp_path):
    """An unnamed artefact cannot say where it belongs, so nothing may guess
    on its behalf."""
    bad = tmp_path / "overview.json"
    bad.write_text('{"ok": true}')
    with pytest.raises(SystemExit) as e:
        drive_fetch.push_artifact("x", str(bad))
    assert "taxonomy name" in str(e.value)
    assert "artifact_store.py put" in str(e.value), "must name the fix"


def test_push_artifact_refuses_a_body_that_contradicts_its_name(monkeypatch, tmp_path):
    """Two sources agreeing and one dissenting is a refusal, never a majority
    vote — writing it anywhere leaves the tree lying about what it holds."""
    local = tmp_path / _named(page="overview", section="hero")
    local.write_text('{"run_id": "7a6ad71c-0000-0000-0000-000000000000", '
                     '"page": "heatmap"}')
    with pytest.raises(SystemExit) as e:
        drive_fetch.push_artifact("x", str(local))
    assert "heatmap" in str(e.value)


def test_push_artifact_refuses_invalid_json(tmp_path):
    local = tmp_path / _named()
    local.write_text("{not json")
    with pytest.raises(SystemExit) as e:
        drive_fetch.push_artifact("x", str(local))
    assert "valid JSON" in str(e.value)


def test_push_artifact_reports_a_local_misfile_and_still_routes_home(
        monkeypatch, tmp_path, capsys):
    """The healing case: the file is in the wrong local folder, its name is
    right, and the remote copy lands where the name says."""
    root = tmp_path / "artifacts"
    wrong = root / "30_heatmap" / "focus" / "overview-hero-producer"
    wrong.mkdir(parents=True)
    local = wrong / _named()
    local.write_text('{"ok": true}')
    tree = {"root": [], "bundle-root": []}
    created = _bundle_rig(monkeypatch, tmp_path, tree)
    assert drive_fetch.push_artifact("x", str(local), str(root)) == 0
    out = capsys.readouterr().out
    assert "locally filed under" in out and "heal" in out
    assert "10_overview" in created


def _find_rig(monkeypatch, tree, insights_name="DMAI - X"):
    monkeypatch.setattr(drive_fetch, "_token", lambda: "tok")
    monkeypatch.setattr(drive_fetch, "_find_client_folder",
                        lambda tok, c: {"id": "root", "name": "X - DMA"})

    def boom(*a, **k):
        raise AssertionError("a read-only search created a folder")
    monkeypatch.setattr(drive_fetch, "_ensure_folder", boom)
    monkeypatch.setattr(drive_fetch, "_insights_root", boom)
    monkeypatch.setattr(drive_fetch, "_list_children",
                        lambda tok, fid: tree.get(fid, []))


def _folder(fid, name):
    return {"id": fid, "name": name, "mimeType": drive_fetch.FOLDER_MIME}


def _file(fid, name):
    return {"id": fid, "name": name, "mimeType": "application/json"}


def test_find_artifact_searches_the_whole_tree_not_just_the_right_folder(
        monkeypatch, capsys):
    """RECURSIVE, and the misfiled case is the reason. A lookup that reads
    only the correct folder reports misplaced work as absent, which is the
    exact condition under which it gets produced a second time."""
    name = _named()
    tree = {
        "root": [_folder("ins", "DMAI - X")],
        "ins": [_folder("hm", "30_heatmap")],
        "hm": [_folder("f", "focus")],
        "f": [_folder("a", "some-other-producer"), _file("x1", name)],
        "a": [],
    }
    _find_rig(monkeypatch, tree)
    assert drive_fetch.find_artifact("x", run="7a6ad71c") == 0
    out = capsys.readouterr().out
    assert "overview/hero" in out
    assert "MISFILED" in out, "found, and told it is in the wrong place"


def test_find_artifact_filters_on_every_taxonomy_field(monkeypatch, capsys):
    tree = {
        "root": [_folder("ins", "DMAI - X")],
        "ins": [_folder("ov", "10_overview")],
        "ov": [_folder("h", "hero")],
        "h": [_folder("p", "overview-hero-producer")],
        "p": [_file("x1", _named(kind="payload", ts="20260821T050000Z")),
              _file("x2", _named(kind="challenge", ts="20260821T060000Z"))],
    }
    _find_rig(monkeypatch, tree)
    drive_fetch.find_artifact("x", page="overview", kind="challenge")
    out = capsys.readouterr().out
    assert "challenge" in out and "payload" not in out
    assert "MISFILED" not in out


def test_find_artifact_reports_no_folder_rather_than_creating_one(
        monkeypatch, capsys):
    """A search that creates what it reports on makes every client compliant
    on its first run and agrees with itself forever after — the same defect
    ingestion_status.py exists to avoid. `_ensure_folder` and `_insights_root`
    are booby-trapped in the rig; reaching either fails the test."""
    _find_rig(monkeypatch, {"root": []})
    assert drive_fetch.find_artifact("x") == 0
    assert "ensure-insights" in capsys.readouterr().out


def test_find_artifact_says_nothing_matched_without_saying_nothing_was_done(
        monkeypatch, capsys):
    tree = {"root": [_folder("ins", "DMAI - X")], "ins": []}
    _find_rig(monkeypatch, tree)
    drive_fetch.find_artifact("x", run="deadbeef")
    out = capsys.readouterr().out
    assert "has not been filed" in out and "not the same as not done" in out


def test_the_taxonomy_is_never_restated_in_drive_fetch():
    """One authority for the page/section/agent mapping. A second copy is a
    second thing to drift, and asserted over AST constants with docstrings
    excluded, because the comments here explain the rule and a substring
    check would match its own explanation."""
    import ast
    src = (HERE / "drive_fetch.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            d = ast.get_docstring(node, clean=False)
            if d:
                docstrings.add(d)
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and n.value not in docstrings]
    for lit in literals:
        assert "10_overview" not in lit and "30_heatmap" not in lit, (
            f"the folder taxonomy is restated in a literal: {lit!r}")
