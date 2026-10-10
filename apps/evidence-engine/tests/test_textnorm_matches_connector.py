"""The copied extractor and normalisation never drift from the connector's.

Imports `apps/mcp/dma_mcp/fetching.py` and `register.py` by path when the
checkout is present (CI has it); skips otherwise. The research ledger's
copy (`engine/fetch.py`) is pinned to the connector by its own test, so
pinning here to the connector pins all three."""
import importlib.util
import re
from pathlib import Path

import pytest

from evidence_engine import textnorm

ROOT = Path(__file__).resolve().parents[3]
FETCHING = ROOT / "apps" / "mcp" / "dma_mcp" / "fetching.py"
REGISTER = ROOT / "apps" / "mcp" / "dma_mcp" / "register.py"

SAMPLE = """<html><head><title>T</title><style>p{}</style><script>x=1</script></head>
<body><nav>Home</nav><h1>Example <b>Fin</b>ancial</h1><p>At December 31, 2025, we had
<ix:nonFraction name="a">$1,775.6</ix:nonFraction> billion &amp; growing.</p>
<table><tr><td>a</td><td>b</td></tr></table><!-- c --><p>Second&nbsp;para.</p></body></html>"""


def _load(path: Path, name: str):
    if not path.exists():
        pytest.skip(f"{path} not in this checkout")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"connector module not importable here: {exc}")
    return mod


def test_html_extractor_is_byte_identical_to_the_connectors():
    fetching = _load(FETCHING, "dma_fetching")
    assert textnorm.connector_html_text(SAMPLE) == fetching._html_text(SAMPLE)


def test_html_extractor_source_text_is_identical():
    """Stronger than one sample: the function body itself is the same."""
    if not FETCHING.exists():
        pytest.skip("no checkout")
    src = FETCHING.read_text(encoding="utf-8")
    m = re.search(r"def _html_text\(markup: str\) -> str:.*?return _html\.unescape\(s\)", src, re.S)
    assert m, "connector _html_text not found"
    theirs = m.group(0).split('"""')[-1].replace("import html as _html", "")
    import inspect
    mine = inspect.getsource(textnorm.connector_html_text).split('"""')[-1]
    norm = lambda s: re.sub(r"\s+", " ", s).strip()  # noqa: E731
    assert norm(mine) == norm(theirs)


def test_normalise_agrees_with_register_evidence():
    """register.py cannot be imported standalone (relative imports), so the
    rule is pinned by its SOURCE: whitespace collapsed, stripped, lower-cased
    — and ours differs only by casefold, which is stricter."""
    if not REGISTER.exists():
        pytest.skip("no checkout")
    src = REGISTER.read_text(encoding="utf-8")
    m = re.search(r"def _normalise\(text: str\) -> str:\s*\n\s*return (.+)", src)
    assert m, "register._normalise not found"
    assert m.group(1).strip() == 're.sub(r"\\s+", " ", text or "").strip().lower()'
    for s in ("  Hello   World \n foo", "a\tb\nc"):
        theirs = re.sub(r"\s+", " ", s or "").strip().lower()
        assert textnorm.normalise(s) == theirs


def test_pdf_fold_matches_the_connectors_table():
    fetching = _load(FETCHING, "dma_fetching2")
    src = FETCHING.read_text(encoding="utf-8")
    pairs = re.findall(r'\("(.)", "(.{1,3})"\)', src.split("def _pdf_text")[1].split("return text")[0])
    assert pairs, "ligature table not found"
    for lig, plain in pairs:
        assert textnorm.connector_pdf_fold(lig) == plain


def test_sentences_cover_text_and_respect_abbreviations():
    text = "Dr. Smith joined in 2024. The bank, est. 1901, grew 4% in Q1. Next line.\n\nNew para here."
    spans = textnorm.sentences(text)
    sents = [text[s:e] for s, e in spans]
    assert sents == ["Dr. Smith joined in 2024.", "The bank, est. 1901, grew 4% in Q1.",
                     "Next line.", "New para here."]
    for s, e in spans:
        assert text[s:e] == text[s:e].strip()
