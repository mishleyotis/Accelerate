# DMA Assessment Automation Script Suite

**Version**: 1.0
**Description**: Consulting-grade operating system for the DMA assessment skill. Automates evidence ingestion, indexing, retrieval, batch scoring, QA auditing, and evaluation.

## Overview

This script suite implements a production-grade pipeline for Digital Maturity Assessments (DMA). It operationalizes the dma-assessment skill through:

1. **Evidence Ingestion** - Extract text from PDF/DOCX/PPTX/TXT/CSV documents
2. **Indexing** - Build BM25 retrieval index with smart tokenization
3. **Query Generation** - Generate taxonomy-aware queries for subcapabilities
4. **Batch Scoring** - Score all 851 subcapabilities (full scope) with caching and checkpointing
5. **QA Auditing** - Validate workbooks for compliance and quality
6. **Retrieval Evaluation** - Measure retrieval quality against test sets

## Scripts

### 1. `ingest_evidence.py`

Extract and chunk evidence documents.

**Features**:
- Multi-format extraction: PDF (pdfplumber), DOCX (python-docx), PPTX (python-pptx), TXT, MD, CSV
- Configurable chunking (default 1200 chars, 200 char overlap)
- Auto-detect evidence tier from filename/path patterns:
  - **T1**: exam, 10-k, annual report, sec filing, audit, consent order, enforcement, call report
  - **T2**: policy, procedure, strategy, board, investor, governance
  - **T3**: analyst, rating, benchmark, jd power, app store, news
  - **T4**: interview, workshop, internal, training, project
  - **T5**: press release, marketing, website, social, promo
- Auto-detect institution and date from filenames
- Stable chunk IDs: `sha256(path + mtime)[:16]:chunk_number`
- Output: `evidence_corpus.parquet` with columns:
  - `chunk_id`, `source_path`, `source_id`, `source_filename`, `tier`, `institution`, `as_of_date`, `text`, `text_hash`, `char_count`

**Usage**:
```bash
python ingest_evidence.py --root /path/to/docs --out corpus.parquet
python ingest_evidence.py --root /path/to/docs --chunk-size 1500 --overlap 250
```

**Args**:
- `--root` (required): Root directory to scan
- `--out` (default: `evidence_corpus.parquet`): Output file
- `--chunk-size` (default: 1200): Characters per chunk
- `--overlap` (default: 200): Overlap between chunks

### 2. `build_index.py`

Build BM25 hybrid retrieval index.

**Features**:
- BM25Okapi with smart tokenization (lowercase, remove stopwords, min length 3)
- Incremental rebuild: only re-index changed chunks (compare `text_hash`)
- Corpus hash detection to avoid unnecessary rebuilds
- Output files:
  - `bm25.pkl`: Pickled BM25 model
  - `meta.pkl`: Index metadata (indexed chunks, corpus hash)
  - `texts.parquet`: Chunk texts with IDs and metadata

**Usage**:
```bash
python build_index.py --corpus evidence_corpus.parquet --out-dir ./index
python build_index.py --corpus evidence_corpus.parquet --out-dir ./index --force-rebuild
```

**Args**:
- `--corpus` (required): Path to corpus parquet
- `--out-dir` (default: `./index`): Output directory
- `--force-rebuild` (flag): Force rebuild even if unchanged

### 3. `retrieve.py`

Retrieval engine with evidence pack generation.

**Features**:
- BM25 search with configurable k
- Diversify: enforce max results per tier
- Deduplicate: remove exact/near-duplicate results
- Evidence pack builder: generates compact packs with tier distribution and coverage scores
- Supports multi-angle queries (canonical, controls, metrics, operating model)

**Classes**:
- `Retriever`: Main retrieval class
  - `search(query, k=20)`: Search chunks
  - `diversify(results, max_per_tier=3)`: Enforce tier diversity
  - `deduplicate(results)`: Remove duplicates
  - `build_evidence_pack(subcap_id, subcap_name, diagnostic_questions, k=15)`: Generate pack

**Usage**:
```bash
# CLI search
python retrieve.py --index-dir ./index --query "digital transformation"

# Evidence pack generation
python retrieve.py --index-dir ./index \
    --subcap-id P1C1 \
    --subcap-name "Digital Strategy & Vision"

# Python API
from retrieve import Retriever
retriever = Retriever("./index")
results = retriever.search("digital strategy", k=20)
pack = retriever.build_evidence_pack("P1C1", "Digital Strategy & Vision")
```

**Output Format** (Evidence Pack):
```json
{
    "subcap_id": "P1C1",
    "subcap_name": "Digital Strategy & Vision",
    "chunks": [
        {
            "chunk_id": "abc123:0",
            "text": "...",
            "tier": "T1",
            "source_id": "SRC-000001",
            "score": 8.5
        }
    ],
    "tier_distribution": {"T1": 2, "T2": 3, "T3": 2},
    "coverage_score": 0.85
}
```

### 4. `subcap_query_builder.py`

Generate taxonomy-aware queries.

**Features**:
- Load Pillar XLSX files from `/mnt/project/`
- Generate 4 query types per subcapability:
  1. **canonical**: subcap name + capability + category
  2. **controls**: governance, policy, framework
  3. **metrics**: KPI, dashboard, measurement, analytics
  4. **operating_model**: process, workflow, automation
- Output: `subcap_queries.json` mapping `subcap_id -> [query1, query2, query3, query4]`

**Usage**:
```bash
python subcap_query_builder.py --pillar-dir /path/to/pillars --out subcap_queries.json
```

**Args**:
- `--pillar-dir` (required): Directory with Pillar*.xlsx files
- `--out` (default: `subcap_queries.json`): Output file

**Output Format**:
```json
{
    "P1C1": {
        "canonical": "Digital Strategy & Vision Strategic Leadership Planning",
        "controls": "Digital Strategy & Vision controls governance policy framework",
        "metrics": "Digital Strategy & Vision KPI metrics measurement dashboard analytics",
        "operating_model": "Digital Strategy & Vision process workflow automation orchestration"
    }
}
```

### 5. `assessment_runner.py`

Batch scoring orchestrator.

**Features**:
- Load taxonomy from Pillar XLSX files
- Process by pillar batch with checkpointing: P1 → save → P2 → save → P3 → save → P4 → save
- Pluggable LLM scoring function (stub provided)
- Evidence-linked scoring with rationale
- Aggregation chain: subcap → capability → category → pillar → overall
- Apply caps cascade: evidence, severity, sentiment, cross-pillar dependencies
- Export to Excel workbook with 8+ sheets:
  - Summary
  - Calculation_Chain
  - P1/P2/P3/P4_Scoring_Detail
  - Evidence_Index
  - Caps_Applied_Log
  - Contradiction_Log

**Pluggable Scorer**:
```python
def custom_scorer(subcap_id, subcap_name, evidence_pack):
    # Call your LLM API here
    return {
        "score": 3.5,
        "rationale": "Evidence shows...",
        "evidence_ids": ["chunk_id_1", "chunk_id_2"],
        "confidence": "MEDIUM"
    }

runner = AssessmentRunner(..., scoring_function=custom_scorer)
```

**Usage**:
```bash
python assessment_runner.py \
    --corpus evidence_corpus.parquet \
    --index-dir ./index \
    --pillar-dir /path/to/pillars \
    --institution "My Bank" \
    --sub-vertical "Credit Union" \
    --size-tier "Mega" \
    --out-dir ./assessment_output
```

**Args**:
- `--corpus`: Path to corpus parquet
- `--index-dir`: Path to index directory
- `--pillar-dir`: Path to Pillar XLSX files
- `--institution` (required): Institution name
- `--sub-vertical` (required): Sub-vertical (Credit Union, Regional Bank, etc.)
- `--size-tier` (required): Size tier (Mega, Large, Medium, Small)
- `--out-dir` (default: `./assessment_output`): Output directory

### 6. `qa_auditor.py`

QA governance automation (READ-ONLY).

**Features**:
- Load workbook and run compliance checks:
  - **Row Counts**: Verify pillar row counts within ±5% of expected
  - **Score Bounds**: Ensure 1.0-5.0 with max 1 decimal place
  - **Evidence Linkage**: Every score has evidence IDs
  - **Caps Consistency**: Capped scores have log entries
  - **Rationale Quality**: Min 150 chars, contains evidence ID reference
  - **Weight Sums**: Aggregation weights sum to 1.0
  - **Distributional Checks**: Score uniformity, confidence calibration
- Output severity: CRITICAL (fail), HIGH (warnings), MEDIUM/LOW (notes)
- Output files:
  - `issue_register.csv`: All issues with severity and details
  - `qa_verdict.json`: Summary with verdict (PASS/PASS_WITH_NOTES/FAIL)
  - `patch_block.md`: Markdown report for remediation

**Usage**:
```bash
python qa_auditor.py --workbook assessment.xlsx --out-dir ./qa_results
```

**Args**:
- `--workbook` (required): Path to assessment Excel file
- `--out-dir` (default: `./qa_results`): Output directory

**Verdict Rules**:
- **FAIL**: Any CRITICAL issues open
- **PASS_WITH_NOTES**: HIGH issues open, no CRITICAL
- **PASS**: Only MEDIUM/LOW issues

### 7. `eval_retrieval.py`

Retrieval quality evaluation harness.

**Features**:
- Load labeled test set (query → expected_source_ids)
- Run retrieval for each query
- Compute metrics:
  - **Recall@k**: recall@5, recall@10, recall@20
  - **MRR**: Mean Reciprocal Rank
  - **Tier Diversity**: Score measuring distribution across T1-T5
  - **Recency Coverage**: Percentage of recent results
- Compare to baseline
- Output: `eval_results.json` with detailed metrics

**Labeled Test Set Format**:
```json
{
    "queries": [
        {
            "query": "digital transformation strategy",
            "expected_source_ids": ["SRC-000001", "SRC-000002", "SRC-000005"]
        },
        {
            "query": "compliance controls",
            "expected_source_ids": ["SRC-000003", "SRC-000004"]
        }
    ]
}
```

**Usage**:
```bash
python eval_retrieval.py \
    --labeled-set test_queries.json \
    --index-dir ./index \
    --out eval_results.json

# With baseline comparison
python eval_retrieval.py \
    --labeled-set test_queries.json \
    --index-dir ./index \
    --baseline previous_eval.json \
    --out eval_results.json
```

**Args**:
- `--labeled-set` (required): Path to test set JSON
- `--index-dir` (required): Path to index directory
- `--baseline`: Path to baseline results for comparison
- `--out` (default: `eval_results.json`): Output file

## Makefile

Orchestration targets for the full pipeline.

**Variables**:
```makefile
DOCS_ROOT ?= ./documents          # Documents to ingest
INSTITUTION ?= Test_Institution   # Institution name
SUB_VERTICAL ?= Credit Union      # Sub-vertical
SIZE_TIER ?= Mega                 # Size tier
OUT_DIR ?= ./assessment_output    # Output directory
INDEX_DIR ?= ./index              # Index directory
PILLAR_DIR ?= /mnt/project        # Pillar XLSX files
```

**Targets**:
- `make install` - Install dependencies
- `make ingest` - Ingest documents
- `make index` - Build BM25 index
- `make queries` - Generate subcapability queries
- `make run` - Run batch assessment
- `make audit` - Run QA audit
- `make eval` - Evaluate retrieval
- `make all` - Run full pipeline: ingest → index → queries → run → audit
- `make clean` - Remove generated files
- `make print-config` - Display configuration
- `make help` - Show help

**Examples**:
```bash
# Full pipeline
make all DOCS_ROOT=/path/to/docs INSTITUTION="My Bank" SUB_VERTICAL="Credit Union"

# Just run assessment
make run INSTITUTION="My Bank" SUB_VERTICAL="Regional Bank" SIZE_TIER="Large"

# Audit existing workbook
make audit OUT_DIR=./previous_assessment

# Clean and start fresh
make clean all DOCS_ROOT=/path/to/docs
```

## Installation

### Requirements

- Python 3.9+
- Dependencies in `requirements.txt`:
  - pandas 2.0.3
  - pyarrow 12.0.0
  - openpyxl 3.10.10
  - rank-bm25 0.2.2
  - python-docx 0.8.11
  - pdfplumber 0.9.0
  - python-pptx 0.6.21
  - matplotlib 3.7.2
  - numpy 1.24.3
  - python-dateutil 2.8.2

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Or use Makefile
make install
```

### Platforms

Scripts work in:
- **Cowork VM** (Linux sandbox)
- **Local Python** (3.9+)
- **CI Runners** (GitHub Actions, GitLab CI)

## Design Principles

1. **Idempotent**: All operations cache and skip unnecessary work
2. **Token-Efficient**: Batching, checkpointing, and early saves minimize context loss
3. **Auditable**: Full traceability with evidence IDs and citation chains
4. **Pluggable**: Scoring function easily replaced with real LLM calls
5. **Production-Grade**: Comprehensive error handling, logging, progress reporting

## Usage Examples

### Full Assessment Pipeline

```bash
make all \
    DOCS_ROOT=/home/docs/navy_federal \
    INSTITUTION="Navy Federal Credit Union" \
    SUB_VERTICAL="Credit Union" \
    SIZE_TIER="Mega" \
    PILLAR_DIR=/mnt/project
```

This runs:
1. Ingests all documents from `/home/docs/navy_federal`
2. Builds BM25 index
3. Generates queries from Pillar XLSX files
4. Scores all 851 subcapabilities (full scope)
5. Audits the resulting workbook
6. Outputs workbook, QA results, and visualizations to `./assessment_output`

### Incremental Updates

```bash
# Only re-ingest changed documents
make ingest DOCS_ROOT=/home/docs/navy_federal

# Rebuild index only (uses cached corpus)
make index

# Re-score with new evidence (using cached queries)
make run INSTITUTION="Navy Federal" SUB_VERTICAL="Credit Union"
```

### Retrieval Evaluation

```bash
# Create test set
cat > test_queries.json << 'EOF'
{
    "queries": [
        {
            "query": "digital transformation strategy",
            "expected_source_ids": ["SRC-000001", "SRC-000002"]
        }
    ]
}
EOF

# Evaluate
make eval

# Compare to baseline
python eval_retrieval.py \
    --labeled-set test_queries.json \
    --index-dir ./index \
    --baseline previous_eval.json \
    --out eval_results.json
```

## API Usage

### Python Imports

```python
# Evidence ingestion
from ingest_evidence import EvidenceExtractor
extractor = EvidenceExtractor(chunk_size=1200, overlap=200)
df = extractor.ingest_directory("/path/to/docs")

# Indexing
from build_index import BM25IndexBuilder
builder = BM25IndexBuilder()
builder.build("corpus.parquet", "./index")

# Retrieval
from retrieve import Retriever
retriever = Retriever("./index")
results = retriever.search("digital strategy", k=20)
pack = retriever.build_evidence_pack("P1C1", "Digital Strategy & Vision")

# Assessment
from assessment_runner import AssessmentRunner
runner = AssessmentRunner("My Bank", "Credit Union", "Mega")
workbook = runner.run("corpus.parquet", "./index", "/path/to/pillars", "./output")

# QA Auditing
from qa_auditor import QAAuditor
auditor = QAAuditor()
auditor.run_all_checks("assessment.xlsx")
auditor.save_report("./qa_results")

# Retrieval Evaluation
from eval_retrieval import RetrievalEvaluator
evaluator = RetrievalEvaluator("./index")
labeled_set = evaluator.load_labeled_set("test_queries.json")
results = evaluator.evaluate_all(labeled_set)
```

## Architecture

```
Documents
    ↓
[ingest_evidence.py]
    ↓
evidence_corpus.parquet (chunks with text_hash, tier, institution, date)
    ↓
[build_index.py] ← (checks corpus_hash for incremental updates)
    ↓
Index Directory (bm25.pkl, meta.pkl, texts.parquet)
    ↓
[retrieve.py] ← [subcap_query_builder.py] (generates queries)
    ↓
Evidence Packs (per-subcapability retrieval results)
    ↓
[assessment_runner.py] (with pluggable scoring function)
    ↓
Scoring Results (checkpoints per pillar)
    ↓
[assessment_runner.py] (aggregation + caps cascade)
    ↓
Assessment Workbook (Excel with 8+ sheets)
    ↓
[qa_auditor.py]
    ↓
QA Report (issue_register.csv, qa_verdict.json, patch_block.md)
```

## Development

### Error Handling

All scripts include:
- Input validation with clear error messages
- Logging at INFO/WARNING/ERROR levels
- Graceful failure modes (skip problematic files, continue)
- Progress reporting

### Testing

```bash
# Run QA on generated workbook
make audit

# Evaluate retrieval quality
make eval

# Print configuration
make print-config
```

### Logging

Scripts use Python's `logging` module at INFO level. Set `LOGLEVEL=DEBUG` for verbose output:

```bash
LOGLEVEL=DEBUG python ingest_evidence.py --root /path/to/docs
```

## Performance Considerations

- **Chunking**: Default 1200 chars with 200 overlap. Adjust per document type.
- **BM25 Index**: Builds from scratch if corpus changes (detected via hash).
- **Incremental Scoring**: Checkpoints after each pillar; resume with `--resume-from`.
- **Token Efficiency**: Batching in `assessment_runner.py` prevents context overflow.

## License & Attribution

Part of the Zennify Digital Maturity Assessment consulting-grade operating system.

Implements the dma-assessment skill methodology:
- Argument-based reasoning (CLAIM → EVIDENCE → REASONING)
- Evidence triangulation with tier weights
- Caps cascade (severity, evidence, sentiment, cross-pillar)
- Strategic "So What?" analysis per capability

## Support

For issues or questions:
1. Check logs in script output
2. Review `qa_verdict.json` for compliance details
3. Verify inputs: corpus parquet, index directory, pillar files
4. See specific script docstrings for detailed methodology
