"""Gate A's negative control: the three ways past a literal-import regex.

AUD-0047 measured invariant 1's gate matching the TEXT of an import
statement, and named three evasions that reach a live inference endpoint and
pass it. None is exotic; each is ordinary Python that happens not to spell
the import."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "gate_a_no_inference_imports.py"

EVASIONS = {
    "dynamic_concat": 'import importlib\n'
                      'def go():\n'
                      '    return importlib.import_module("anthr" + "opic")\n',
    "direct_endpoint": 'import httpx\n'
                       'def go():\n'
                       '    return httpx.post('
                       '"https://api.anthropic.com/v1/messages", json={})\n',
    "runtime_name": 'import os\n'
                    'def go():\n'
                    '    return __import__(os.environ["LLM_SDK"])\n',
}


def _gate_over(tree: Path):
    src = GATE.read_text().replace(
        "ROOT = Path(__file__).resolve().parent.parent",
        f"ROOT = Path({str(tree)!r})")
    probe = tree / "gate_probe.py"
    probe.write_text(src)
    return subprocess.run([sys.executable, str(probe)],
                          capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("name,body", sorted(EVASIONS.items()))
def test_each_evasion_fails_the_gate(tmp_path, name, body):
    (tmp_path / "apps" / "api").mkdir(parents=True)
    (tmp_path / "apps" / "api" / f"{name}.py").write_text(body)
    r = _gate_over(tmp_path)
    assert r.returncode == 1, f"{name} passed the gate:\n{r.stdout}"
    assert name in r.stdout


def test_the_literal_import_still_fails(tmp_path):
    (tmp_path / "apps" / "api").mkdir(parents=True)
    (tmp_path / "apps" / "api" / "plain.py").write_text("import anthropic\n")
    assert _gate_over(tmp_path).returncode == 1


def test_the_permitted_local_embedding_model_still_passes(tmp_path):
    """The ONLY sanctioned model use: the local sentence-embedding model in
    the connector and worker. A gate that blocked it would break the vector
    tier the TRD requires."""
    (tmp_path / "apps" / "mcp").mkdir(parents=True)
    (tmp_path / "apps" / "mcp" / "embed.py").write_text(
        "import onnxruntime\n"
        "from sentence_transformers import SentenceTransformer\n")
    r = _gate_over(tmp_path)
    assert r.returncode == 0, r.stdout


def test_a_test_file_walking_its_own_imports_is_not_a_violation(tmp_path):
    """apps/worker/tests/test_enrichment_loop.py parses an AST and imports
    what it finds — the OPPOSITE of evading the gate. A gate that cries wolf
    on its own suite gets switched off."""
    (tmp_path / "apps" / "worker" / "tests").mkdir(parents=True)
    (tmp_path / "apps" / "worker" / "tests" / "test_x.py").write_text(
        "import importlib\n"
        "def test_y():\n"
        "    importlib.import_module(node.module)\n")
    assert _gate_over(tmp_path).returncode == 0


def test_the_real_repository_passes():
    r = subprocess.run([sys.executable, str(GATE)], capture_output=True,
                       text=True, timeout=180)
    assert r.returncode == 0, r.stdout
