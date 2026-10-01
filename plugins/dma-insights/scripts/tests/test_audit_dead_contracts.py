"""The dead-contracts audit finds a writer with no reader, and the shipped
plugin has none.

Measured 28-09-2026 (QA audit F-J02-011): six artefacts had a writer and no
reader, found by hand. These tests plant each shape in a scratch plugin
tree — an orphan, a code reader, a documentary reader, a module reading its
own artefact back, and a stress walk's scratch — and expect the audit to
classify each as the audit's docstring says; the last test is the point.
"""
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("audit_dead_contracts",
                                               SCRIPTS / "audit_dead_contracts.py")
adc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(adc)


def _plant(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _tree(tmp_path):
    root = tmp_path / "plugins" / "dma-insights"
    root.mkdir(parents=True)
    return root


def _status(out, token):
    return next(r["status"] for r in out["artefacts"] if r["artefact"] == token)


def test_a_writer_with_no_reader_is_an_orphan(tmp_path):
    root = _tree(tmp_path)
    _plant(root, "skills/x/w.py", 'Path(qa) / "07_qa" / "lonely.json"\nout.write_text(json.dumps(doc))\n')
    out = adc.audit(root)
    assert _status(out, "lonely.json") == "ORPHAN"
    assert out["orphans"] == ["lonely.json"]


def test_a_code_reader_a_doc_reader_and_a_read_back_are_not(tmp_path):
    root = _tree(tmp_path)
    _plant(root, "skills/x/w.py", '(qa / "read.json").write_text("{}")\n'
                                  '(qa / "doc.json").write_text("{}")\n'
                                  'NAME = "mine.json"\n'
                                  '(qa / NAME).write_text("{}")\n'
                                  'json.loads((qa / NAME).read_text())\n')
    _plant(root, "skills/y/r.py", 'json.loads((qa / "read.json").read_text())\n')
    _plant(root, "agents/a.md", "Read `07_qa/doc.json` before you write a word.\n")
    out = adc.audit(root)
    assert _status(out, "read.json") == "READ"
    assert _status(out, "doc.json") == "DOC-ONLY"
    assert _status(out, "mine.json") == "READ"
    assert out["orphans"] == [] and out["doc_only"] == ["doc.json"]


def test_a_stress_walks_scratch_and_a_test_are_not_contracts(tmp_path):
    root = _tree(tmp_path)
    _plant(root, "scripts/stress_thing.py", '(tmp / "scratch.json").write_text("{}")\n')
    _plant(root, "scripts/tests/test_x.py", '(tmp / "fixture.json").write_text("{}")\n')
    out = adc.audit(root)
    assert out["artefacts"] == []


def test_a_dynamic_name_is_not_claimed(tmp_path):
    root = _tree(tmp_path)
    _plant(root, "skills/x/w.py", '(qa / f"{agent}-{ts}.json").write_text("{}")\n')
    assert adc.audit(root)["artefacts"] == []


def test_strict_exit_codes(tmp_path):
    root = _tree(tmp_path)
    _plant(root, "skills/x/w.py", '(qa / "lonely.json").write_text("{}")\n')
    assert adc.main(["--strict", "--root", str(root)]) == 1
    assert adc.main(["--root", str(root)]) == 0
    _plant(root, "skills/y/r.py", '(qa / "lonely.json").read_text()\n')
    assert adc.main(["--strict", "--root", str(root)]) == 0


def test_the_shipped_plugin_has_no_orphan():
    out = adc.audit()
    assert out["orphans"] == [], out["orphans"]
