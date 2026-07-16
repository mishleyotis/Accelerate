# DMA Insights workers — shared image for drive_crawler, sheet_poller,
# embedder, and ccg_loader Cloud Run Jobs.
#
# Each job's command is selected at Cloud Run Job creation time via the
# `command` + `args` fields (see infra/terraform/jobs.tf). This keeps
# us at one image per artifact instead of four.
#
# State-branch contract:
#   --dry-run        → parsers + validators run, no live IO
#   --once / --run-id → live IO (Drive v3, Sheets v4, Vertex SDK)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# System deps:
#   libpq5 / libxml2 / libxslt1.1  — base Python C extensions
#   tesseract-ocr / libtesseract-dev / poppler-utils — OCR fallback for
#     retry-mode deep extraction (§50). pytesseract + pdf2image are the
#     Python shims; without these system binaries they raise on first
#     call and `deep_extract` returns ("", 0). With them, the retry
#     pass can recover scoreable content from image-only DOCX / PDFs.
#   The image grows by ~120 MB; acceptable for the once-per-deploy cost.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 libxml2 libxslt1.1 \
        tesseract-ocr libtesseract-dev poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash app

WORKDIR /home/app
COPY backend/pyproject.toml ./pyproject.toml
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
        "sqlalchemy[asyncio]==2.0.35" "asyncpg==0.29.0" \
        "psycopg[binary]==3.2.3" "pgvector==0.3.6" \
        "pydantic[email]==2.9.2" "pydantic-settings==2.5.2" \
        "redis[hiredis]==5.1.1" \
        "google-auth==2.35.0" "google-cloud-aiplatform==1.70.0" \
        "google-api-python-client==2.149.0" \
        "google-cloud-secret-manager==2.21.0" \
        "google-cloud-storage==2.18.2" "google-cloud-pubsub==2.26.0" \
        "openpyxl==3.1.5" "python-docx==1.1.2" \
        "pytesseract==0.3.13" "pdf2image==1.17.0" "Pillow==10.4.0" \
        "structlog==24.4.0" "tenacity==9.0.0" "rapidfuzz==3.10.0" \
        "scikit-learn==1.5.2" "scipy==1.13.1" "spacy==3.7.5" \
        "zstandard==0.25.0" \
        "httpx==0.27.2" "beautifulsoup4==4.12.3" "lxml==5.3.0"
# httpx/beautifulsoup4/lxml: the evidence_crawler worker fetches cited pages and
# extracts a cross-encoder-grounded excerpt for evidence rows that arrived with a
# URL but no quote. Versions pinned to the backend pyproject so the two images
# resolve identically.
# NLP tier for workers touching section_analysis / similarity (e.g.
# intelligence_recompute, embedder subscribe). scikit-learn/scipy are
# load-bearing for the similarity linker; the spaCy model is baked
# resiliently — a download failure degrades to the regex tier, never
# breaking the build (mirrors backend.Dockerfile; NLP_DEGRADED contract).
RUN pip install --no-cache-dir \
        "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl" \
        || echo "[nlp] en_core_web_sm not baked — NLP degrades to regex tier"
# MiniLM semantic tier — see backend.Dockerfile. intelligence_recompute +
# the derive/knowledge modules rank evidence SEMANTICALLY here too (not just
# lexical TF-IDF). CPU torch wheel; all-MiniLM-L6-v2 baked to a stable dir,
# loaded OFFLINE at run. SOFT: a transient pytorch.org / HF hiccup degrades
# to the TF-IDF tier (semantic.py never raises) rather than breaking the build.
RUN pip install --no-cache-dir torch==2.13.0 \
        --index-url https://download.pytorch.org/whl/cpu \
     && pip install --no-cache-dir "sentence-transformers==3.0.1" \
     && HF_HOME=/tmp/hfcache python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2').save('/home/app/st-minilm'); CrossEncoder('cross-encoder/stsb-distilroberta-base').save('/home/app/st-ce')" \
     && chmod -R a+rX /home/app/st-minilm /home/app/st-ce \
     && rm -rf /tmp/hfcache \
    || echo "[nlp] MiniLM/cross-encoder not baked — evidence alignment degrades to TF-IDF"
# chmod a+rX is LOAD-BEARING (mirrors backend.Dockerfile): hf-xet writes
# model.safetensors 0600 root-only and .save() preserves it; USER app below
# could not read the weights, silently degrading workers to TF-IDF.
# Two-tier alignment (bi-encoder recall + cross-encoder precision) — see
# backend.Dockerfile. intelligence_recompute + the derive/knowledge modules
# re-rank evidence here too.
ENV DMA_ST_MODEL_DIR="/home/app/st-minilm" \
    DMA_CE_MODEL_DIR="/home/app/st-ce" \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false

COPY backend/app /home/app/app
COPY workers /home/app/workers

USER app

# Default entrypoint runs nothing — Cloud Run Jobs supply `command`.
# Locally: `docker run … python -m workers.embedder.main --dry-run --run-id X`
ENTRYPOINT ["python", "-m"]
