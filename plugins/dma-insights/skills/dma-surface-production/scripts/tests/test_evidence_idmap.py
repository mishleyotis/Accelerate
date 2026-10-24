"""Evidence is registered once; the id map is keyed by the server's own
content hash (QA audit F-O11-036)."""
import hashlib
import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("evidence_idmap", SCRIPTS / "evidence_idmap.py")
im = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(im)

ITEM = {"source_url": "https://acme.example/ar25#p1", "claim_type": "FACT",
        "excerpt": "Alkami   digital banking went live in Q3 2024 and reached 47 percent adoption.",
        "tier": "T2", "source_name": "Annual Report 2025"}


def test_the_hash_is_the_servers_recipe():
    """sha256(url | claim | lower(left(whitespace-collapsed excerpt, 500)))."""
    span = "alkami digital banking went live in q3 2024 and reached 47 percent adoption."
    want = hashlib.sha256(f"{ITEM['source_url']}|FACT|{span}".encode()).hexdigest()
    assert im.item_hash(ITEM) == want
    assert im.item_hash({**ITEM, "excerpt": ITEM["excerpt"].upper()}) == want, "case-insensitive"
    assert im.item_hash({**ITEM, "excerpt": "x" * 600}) == im.item_hash({**ITEM, "excerpt": "x" * 500})
    assert im.item_hash({**ITEM, "claim_type": "INFERENCE"}) != want
    sql = (Path(__file__).resolve().parents[6] / "apps/mcp/dma_mcp/register.py").read_text()
    assert "regexp_replace(%s,'\\s+',' ','g'),500)" in sql and "'sha256'" in sql, (
        "the server recipe this mirrors has moved")


def test_register_sends_only_what_the_map_does_not_hold(tmp_path):
    calls = []

    def call(tool, args):
        calls.append((tool, args))
        return {"e_id": f"E-CC-{len(calls):03d}", "deduped": False}
    m = tmp_path / "07_qa" / "evidence_id_map.json"
    other = {**ITEM, "excerpt": "A different verbatim span of at least fifty characters here."}
    out = im.register("run-1", [ITEM, other, dict(ITEM)], m, call=call)
    assert len(calls) == 2, "the third item is the first item again"
    assert [r["e_id"] for r in out["registered"]] == ["E-CC-001", "E-CC-002"]
    assert out["reused"] == [{"hash": im.item_hash(ITEM)[:12], "e_id": "E-CC-001"}]
    doc = json.loads(m.read_text())
    assert doc[im.item_hash(ITEM)]["e_id"] == "E-CC-001" and doc[im.item_hash(ITEM)]["run_id"] == "run-1"
    # a second session, same items: nothing is sent
    calls.clear()
    again = im.register("run-1", [ITEM, other], m, call=call)
    assert calls == [] and len(again["reused"]) == 2


def test_a_server_dedup_and_an_error_are_recorded_apart(tmp_path):
    def call(tool, args):
        if "fifty" in args["item"]["excerpt"]:
            return {"e_id": None, "errors": ["excerpt_unverified"]}
        return {"e_id": "E-0042", "deduped": True}
    m = tmp_path / "map.json"
    bad = {**ITEM, "excerpt": "A different verbatim span of at least fifty characters here."}
    out = im.register("run-1", [ITEM, bad], m, call=call)
    assert out["deduped_by_server"] == [{"hash": im.item_hash(ITEM)[:12], "e_id": "E-0042"}]
    assert out["errors"][0]["detail"] == ["excerpt_unverified"]
    assert im.item_hash(bad) not in json.loads(m.read_text()), "an error records nothing"


def test_dry_run_calls_nothing_and_writes_nothing(tmp_path):
    m = tmp_path / "map.json"
    out = im.register("run-1", [ITEM], m, call=lambda *a: 1 / 0, dry_run=True)
    assert out["registered"][0]["dry_run"] is True and not m.exists()


def test_the_cli_lookup_and_register(tmp_path, capsys, monkeypatch):
    items = tmp_path / "items.json"
    items.write_text(json.dumps([ITEM]))
    m = tmp_path / "map.json"
    assert im.main(["lookup", str(items), "--map", str(m)]) == 0
    assert json.loads(capsys.readouterr().out)["known"] == 0
    monkeypatch.setattr(im, "_mcp", lambda: (lambda tool, args: {"e_id": "E-CC-007"}))
    assert im.main(["register", "run-1", str(items), "--map", str(m)]) == 0
    assert json.loads(capsys.readouterr().out)["registered"][0]["e_id"] == "E-CC-007"
    assert im.main(["lookup", str(items), "--map", str(m)]) == 0
    assert json.loads(capsys.readouterr().out)["known"] == 1
