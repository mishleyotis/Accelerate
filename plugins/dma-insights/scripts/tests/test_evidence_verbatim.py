"""An excerpt is verbatim or it is absent. There is no third option.

Houlihan Lokey, 2026-08-22. The package-vetter refused the run because
420 of 462 evidence excerpts were not verbatim. They were not *wrong*
extractions — they were not extractions at all. Four independent defects
closed every honest route to a quotation, and one opportunistic fallback
filled the vacuum:

  A  `package_map` classified workbooks by FILENAME. The research workbook
     ships as `02_research_workbook/DMA_Scoring_Workbook_HL.xlsx` — the
     template names every workbook "Scoring" and the FOLDER says which one
     this is. research.primary came back None, so the only store carrying
     `Excerpt`/`Anchor_Quote` columns never entered the reader list.

  C  `_rows_from_json` flattened only the top level of a JSON store. The
     ledger keeps its verbatim spans in `facts: [{fact_id, text}, …]`, so
     the `text` column the vocabulary already knew about was never visible.

  E  `Fact_Summary` (the scoring workbook's column) was in no synonym tuple
     at all. It is a paraphrase and must never be an excerpt — but being
     absent from the vocabulary meant being silently missed rather than
     deliberately refused, which is how the gap opened without a word.

  D  `corpus_fill` then filled that gap by taking ANY corpus line of 50+
     characters that mentioned the evidence id. The line that most reliably
     mentions an evidence id is the ledger record that DEFINES it, so the
     pipeline harvested its own bookkeeping and served it as a quotation
     from a 10-K. 306 of 462 "excerpts" opened with `{"evidence_id": …`.

Measured on the real package, before and after: 462 of 462 excerpts
fabricated → 0; 450 real ones recovered from the two stores that had held
them all along; 12 rows honestly report no excerpt and go out as gaps.

D is the one that matters most, because it survives every fix to A, C and
E: as long as something scavenges prose from proximity, closing the honest
routes only changes which wrong text gets served.
"""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import corpus_search                                          # noqa: E402
import evidence_normalize as en                               # noqa: E402

REAL = ("We do not lend or engage in any securities sales and trading "
        "operations, and we hold no material trading positions.")


def _pkg(tmp_path, files: dict) -> Path:
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body if isinstance(body, str) else json.dumps(body))
    return tmp_path


# ── C · the verbatim span lives one level down ──


#: The real pair, from `01_evidence_index.json` — the assessor's analysis
#: and the span the filing contains. 899 facts in that one package carry
#: both, and not one pair is identical.
ANALYSIS = ('HL explicitly positions its advisory-only independence as its '
            'core strategic differentiator: "We do not lend or engage in '
            'any securities sales and trading operations".')


def test_a_nested_fact_list_yields_its_verbatim_text(tmp_path):
    """The ledger.jsonl shape: one record per id, spans inside `facts`."""
    pkg = _pkg(tmp_path, {"01_evidence/ledger.jsonl": json.dumps({
        "evidence_id": "E-001",
        "source_name": "Houlihan Lokey, Inc. Form 10-K",
        "url": "https://www.sec.gov/x.htm",
        "publish_date": "2025-05",
        "facts": [{"fact_id": "E-001:F1", "anchor_quote": REAL}],
    })})
    records, _ = en.merge(pkg)
    assert records["E-001"]["excerpt"] == REAL
    # the parent's fields still travel with the fact
    assert records["E-001"]["url"] == "https://www.sec.gov/x.htm"
    assert records["E-001"]["date"] == "2025-05"


def test_a_facts_text_is_the_analysis_not_the_quotation(tmp_path):
    """The measurement that overturned this module's own vocabulary: `text`
    was in the excerpt synonyms, and it is the assessor's sentence ABOUT the
    source — long, fluent, and often containing the quote inside it. Taking
    it as the excerpt serves a paraphrase as a quotation, which is the same
    defect as the fabrication, one layer up."""
    pkg = _pkg(tmp_path, {"01_evidence/ledger.jsonl": json.dumps({
        "evidence_id": "E-001",
        "facts": [{"fact_id": "E-001:F1", "text": ANALYSIS,
                   "anchor_quote": REAL}],
    })})
    records, _ = en.merge(pkg)
    assert records["E-001"]["excerpt"] == REAL
    assert records["E-001"]["summary"] == ANALYSIS


def test_a_fact_with_only_analysis_yields_no_excerpt(tmp_path):
    pkg = _pkg(tmp_path, {"01_evidence/ledger.jsonl": json.dumps({
        "evidence_id": "E-002",
        "facts": [{"fact_id": "E-002:F1", "text": ANALYSIS}],
    })})
    records, _ = en.merge(pkg)
    assert not records["E-002"].get("excerpt")
    assert records["E-002"]["summary"] == ANALYSIS


@pytest.mark.parametrize("header,canonical", [
    ("Source Name", "source_name"),
    ("source name", "source_name"),
    ("URL_or_Citation", "url_or_citation"),
    ("Key Facts (F1..)", "key_facts"),
    ("Key Finding", "key_finding"),
    ("Anchor Quote", "anchor_quote"),
])
def test_a_header_written_with_spaces_is_the_same_column(header, canonical):
    """Lowercasing alone left `source name` matching nothing, so the corpus's
    space-separated generation lost its source, url and excerpt columns."""
    assert en._norm_key(header) == canonical


def test_a_spaced_header_actually_reaches_the_record(tmp_path):
    pkg = _pkg(tmp_path, {"01_evidence/register.csv":
                          "Evidence ID,Source Name,Anchor Quote\n"
                          f'E-070,Form 10-K,"{REAL}"\n'})
    records, _ = en.merge(pkg)
    assert records["E-070"]["source"] == "Form 10-K"
    assert records["E-070"]["excerpt"] == REAL


def test_a_nested_fact_does_not_become_its_own_evidence_row(tmp_path):
    """`E-001:F1` folds onto E-001 — a fact is a span OF an id, not a new
    one. Registering it separately would inflate every evidence count."""
    pkg = _pkg(tmp_path, {"01_evidence/ledger.jsonl": json.dumps({
        "evidence_id": "E-001",
        "facts": [{"fact_id": "E-001:F1", "text": REAL},
                  {"fact_id": "E-001:F2", "text": REAL.replace("not", "NOT")}],
    })})
    records, _ = en.merge(pkg)
    assert list(records) == ["E-001"]


# ── E · a summary is recognised, kept, and refused as an excerpt ──


@pytest.mark.parametrize("column", ["fact_summary", "key_finding",
                                    "claim", "summary", "key_extract"])
def test_a_summary_column_never_becomes_an_excerpt(tmp_path, column):
    pkg = _pkg(tmp_path, {"01_evidence/evidence_index.json": json.dumps([{
        "evidence_id": "E-009",
        column: "The firm describes itself as advisory-only and says it "
                "holds no trading positions of any material size.",
    }])})
    records, _ = en.merge(pkg)
    assert not records["E-009"].get("excerpt")
    assert records["E-009"]["summary"].startswith("The firm describes")


def test_a_verbatim_column_still_becomes_an_excerpt(tmp_path):
    """The negative control for the test above — the split must not have
    made every column a summary."""
    pkg = _pkg(tmp_path, {"01_evidence/evidence_index.json": json.dumps([
        {"evidence_id": "E-010", "anchor_quote": REAL},
        {"evidence_id": "E-011", "excerpt": REAL},
    ])})
    records, _ = en.merge(pkg)
    assert records["E-010"]["excerpt"] == REAL
    assert records["E-011"]["excerpt"] == REAL


# ── D · proximity is not a quotation ──


@pytest.fixture
def scavengeable(monkeypatch):
    """A corpus that WOULD answer every scavenging query, so each test
    measures refusal rather than absence."""
    ledger_line = json.dumps({"evidence_id": "E-020", "source_name": "x",
                              "url": "https://real.example/doc.htm",
                              "publish_date": "2026-07-27"})
    monkeypatch.setattr(corpus_search, "search", lambda *a, **k: [
        {"file": "01_evidence/ledger.jsonl",
         "matches": [{"line": 4, "snippet": ledger_line}]}])


def test_corpus_fill_never_invents_an_excerpt(scavengeable):
    """The defect itself. The snippet mentions E-020, clears 50 chars, and
    must still not become its excerpt."""
    records = {"E-020": {"eid": "E-020", "provenance": []}}
    en.corpus_fill(Path("/nonexistent"), records)
    assert not records["E-020"].get("excerpt")


def test_corpus_fill_never_invents_a_date(scavengeable):
    """E-022 acquired 2026-07-27 — the package's own build stamp — scraped
    off a row that merely mentioned it, and carried no marker saying so."""
    records = {"E-020": {"eid": "E-020", "provenance": []}}
    en.corpus_fill(Path("/nonexistent"), records)
    assert not records["E-020"].get("date")


def test_corpus_fill_still_recovers_a_url_and_marks_it(scavengeable):
    """A URL is an opaque identifier that appears literally, so finding one
    on the id's own line is recognition rather than inference. It is still
    marked, so no reader mistakes it for a value the register stated."""
    records = {"E-020": {"eid": "E-020", "provenance": []}}
    assert en.corpus_fill(Path("/nonexistent"), records) == 1
    assert records["E-020"]["url"] == "https://real.example/doc.htm"
    assert records["E-020"]["field_provenance"]["url"]["how"] == "corpus_scan"


def test_a_serialized_record_is_refused_even_from_a_verbatim_column(tmp_path):
    """Belt and braces: the fabricated text is refused by SHAPE too, so a
    store that has already been polluted cannot launder it through the
    `excerpt` column."""
    pkg = _pkg(tmp_path, {"01_evidence/evidence_index.json": json.dumps([{
        "evidence_id": "E-001",
        "excerpt": '{"evidence_id": "E-001", "source_name": "Houlihan '
                   'Lokey, Inc. Form 10-K", "url": "https://sec.gov/x"}',
    }])})
    records, _ = en.merge(pkg)
    assert not records["E-001"].get("excerpt")


def test_prose_that_merely_contains_pipes_is_not_refused(tmp_path):
    """The negative control, and it is a real row: E-482's excerpt is a job
    posting. An earlier version of the shape check read pipes as structure
    and threw away a genuine quotation."""
    posting = ("Platform Engineer | Solutions Engineer | GCP, AWS, "
               "Snowflake, Terraform, SQL, Python, CI/CD | Infrastructure "
               "Automation, Multi-Tenant Environments")
    pkg = _pkg(tmp_path, {"01_evidence/evidence_index.json": json.dumps(
        [{"evidence_id": "E-482", "anchor_quote": posting}])})
    records, _ = en.merge(pkg)
    assert records["E-482"]["excerpt"] == posting


def test_the_fifty_character_floor_still_applies(tmp_path):
    pkg = _pkg(tmp_path, {"01_evidence/evidence_index.json": json.dumps(
        [{"evidence_id": "E-030", "excerpt": "Too short."}])})
    records, _ = en.merge(pkg)
    assert not records["E-030"].get("excerpt")


# ── provenance · a register value and a derived one are distinguishable ──


def test_a_register_value_names_the_store_and_the_column(tmp_path):
    pkg = _pkg(tmp_path, {"01_evidence/evidence_index.json": json.dumps(
        [{"evidence_id": "E-040", "anchor_quote": REAL,
          "publish_date": "2025-05"}])})
    records, _ = en.merge(pkg)
    fp = records["E-040"]["field_provenance"]
    assert fp["excerpt"] == {"how": "register",
                             "store": "01_evidence/evidence_index.json",
                             "column": "anchor_quote"}
    assert fp["date"]["column"] == "publish_date"


def test_a_collection_date_says_it_is_one():
    """Invariant 9: a derived value is never a default that looks like data.
    The collection rung is legitimate and must announce itself."""
    records = {"E-050": {"eid": "E-050"}}
    en.apply_collection_date(records, "2026-07-27", "file name 'x_2026-07.md'")
    fp = records["E-050"]["field_provenance"]["date"]
    assert fp["how"] == "collection"
    assert "x_2026-07.md" in fp["basis"]


def test_a_missing_excerpt_goes_out_as_a_gap_that_says_what_is_needed():
    records = {"E-060": {"eid": "E-060", "url": "https://a", "date": "2025-01",
                         "summary": "the assessors' paraphrase of the claim"}}
    gap = en.gaps_out(records, "houlihan-lokey-inc")[0]
    assert gap["eid"] == "houlihan-lokey-inc:E-060"
    assert "excerpt" in gap["missing"]
    assert "NOT an excerpt" in gap["note"]
    # a summary is the right thing to search WITH, just not to cite
    assert "paraphrase of the claim" in gap["query"]


# ── the real package, when this container has pulled it ──

PKG = Path("/root/.dma/packages/houlihan-lokey-dma")
REALPKG = pytest.mark.skipif(
    not (PKG / "02_research_workbook").is_dir(),
    reason="Houlihan Lokey package not pulled in this container")


@REALPKG
def test_the_real_package_yields_real_excerpts():
    """End to end on the package that produced the refusal. Both stores that
    held the quotations must be reachable, and nothing may be scavenged."""
    import package_map
    m = package_map.map_package(PKG)
    assert m["research"]["primary"].endswith("DMA_Scoring_Workbook_HL.xlsx")

    records, _ = en.merge(PKG)
    assert en.corpus_fill(PKG, records) >= 0
    with_ex = [r for r in records.values() if r.get("excerpt")]
    assert len(with_ex) > 400, f"only {len(with_ex)} excerpts recovered"
    assert not any(en.SERIALIZED_RE.search(r["excerpt"]) for r in with_ex)
    assert all(r["field_provenance"]["excerpt"]["how"] == "register"
               for r in with_ex)
