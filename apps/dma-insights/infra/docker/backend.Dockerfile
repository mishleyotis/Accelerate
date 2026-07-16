# DMA Insights backend — FastAPI + SQLAlchemy 2.0 + Pydantic v2
#
# Two-stage build keeps the runtime image lean (no compilers).
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Install only what the runtime needs. pgvector + asyncpg pull in libpq.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml ./pyproject.toml
RUN pip install --upgrade pip && \
    pip install --prefix=/install \
        "fastapi==0.115.0" "uvicorn[standard]==0.30.6" \
        "sqlalchemy[asyncio]==2.0.35" "asyncpg==0.29.0" \
        "psycopg[binary]==3.2.3" "alembic==1.13.3" \
        "pgvector==0.3.6" "pydantic[email]==2.9.2" "pydantic-settings==2.5.2" \
        "redis[hiredis]==5.1.1" "httpx==0.27.2" \
        "google-auth==2.35.0" "google-cloud-aiplatform==1.70.0" \
        "google-api-python-client==2.149.0" \
        "google-cloud-secret-manager==2.21.0" \
        "google-cloud-storage==2.18.2" "google-cloud-pubsub==2.26.0" \
        "openpyxl==3.1.5" "python-docx==1.1.2" \
        "beautifulsoup4==4.12.3" "lxml==5.3.0" \
        "rapidfuzz==3.10.0" "structlog==24.4.0" "tenacity==9.0.0" \
        "python-multipart==0.0.12" "PyJWT[crypto]==2.9.0" \
        "cryptography==43.0.1" \
        "jinja2==3.1.6" \
        "pytesseract==0.3.13" "pdf2image==1.17.0" "Pillow==10.4.0" \
        "scikit-learn==1.5.2" "scipy==1.13.1" "spacy==3.7.5" \
        "zstandard==0.25.0" \
        "weasyprint==63.1" "pydyf==0.12.1"
# The `nlp` extra (pyproject) is installed here so the derive chain +
# live ingest run the FULL NLP tier in prod, not the degraded regex tier:
# scikit-learn/scipy power the lemma-TF-IDF similarity linker that
# derive_context (timeline dedup), link_evidence_subcaps (heatmap-cell
# grounding), derive_insights (affects[]) and section_analysis depend on.
# Without them those steps used to hard-fail (ModuleNotFoundError) —
# app/services/nlp/similarity.py now also degrades gracefully as belt-and-
# braces. The spaCy en_core_web_sm model is baked resiliently, in a
# three-rung ladder (2026-07-05 hardening — GitHub 403s Cloud Build's
# shared IP pools often enough that the download alone is a flaky build
# input, and a silently-degraded image fails backend-tests-live-pg 40
# minutes later with three cryptic NLP asserts):
#   1. the canonical GitHub release wheel;
#   2. the REPO-VENDORED copy of the SAME wheel
#      (infra/vendor/wheels/ — deterministic, offline-safe);
#   3. degrade to the regex tier (never breaks the build; the live-pg
#      stage's model gate then reports the cause loudly and early).
COPY infra/vendor/wheels/ /tmp/vendor-wheels/
# PIN the shared scientific stack on EVERY later --prefix=/install pip run:
# --prefix installs are INVISIBLE to pip's resolver, so an unpinned re-resolve
# here re-downloads spacy's deps fresh and can overwrite the step-7 tree with
# a different numpy (2026-07-10 build d008b54e: numpy 2.5.1 landed over
# 1.26.4 → thinc ABI crash "numpy.dtype size changed" → live-pg model gate
# exit 10). Same pins, same versions → byte-identical overwrite, no drift.
RUN pip install --prefix=/install "numpy==1.26.4" "spacy==3.7.5" \
        "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl" \
    || pip install --prefix=/install "numpy==1.26.4" "spacy==3.7.5" \
        /tmp/vendor-wheels/en_core_web_sm-3.7.1-py3-none-any.whl \
    || echo "[nlp] en_core_web_sm not baked — NLP degrades to regex tier"
# ── MiniLM semantic tier (gold-standard evidence↔capability alignment) ──
# sentence-transformers + the CPU-only torch wheel (default PyPI torch is
# the multi-GB CUDA build; --index-url pytorch/cpu is ~1/3 the size and
# matches Cloud Run's CPU runtime). The all-MiniLM-L6-v2 weights are baked
# to a stable dir and loaded OFFLINE at run (DMA_ST_MODEL_DIR + HF offline
# flags in the runtime stage) so neither derive nor serve touches
# huggingface.co. Semantic ranking fixes the lexical misattribution TF-IDF
# can't (a privacy notice out-ranking real underwriting evidence on the
# shared word "member"). Install + bake are SOFT: a transient pytorch.org /
# HF hiccup degrades to the TF-IDF tier (semantic.py never raises) instead
# of breaking the build — same resilience contract as the spaCy model.
# ONE resolver pass, EVERYTHING pinned: two separate pip runs let the ST
# line re-resolve torch from default PyPI (the CUDA build — build b4d9dd26
# pulled nvidia-cusparselt/cuda-toolkit over 2.13.0+cpu and the bake
# degraded). "torch==2.13.0+cpu" only exists on the pytorch index, so the
# extra-index pin is deterministic; everything else resolves from PyPI.
# Deterministic ST/CE model rung (2026-07-13): cloudbuild's fetch-nlp-models
# step mirrors the models from the project GCS bucket into
# infra/vendor/st-models/ before this build; the HF bake below is the
# fallback for local/dev builds and a missing mirror. Every outcome echoes
# LOUDLY — the 330b10cd diagnosis burned an hour because a silent tqdm-less
# bake is indistinguishable from a silent failure in the build log.
COPY infra/vendor/st-models/ /tmp/st-models/
RUN pip install --prefix=/install \
        "torch==2.13.0+cpu" "sentence-transformers==3.0.1" \
        "numpy==1.26.4" "scipy==1.13.1" "scikit-learn==1.5.2" "Pillow==10.4.0" \
        --extra-index-url https://download.pytorch.org/whl/cpu \
     && if [ -f /tmp/st-models/st-minilm/config.json ] && [ -f /tmp/st-models/st-ce/config.json ]; then \
          cp -r /tmp/st-models/st-minilm /install/st-minilm \
          && cp -r /tmp/st-models/st-ce /install/st-ce \
          && echo "[nlp] ST/CE models installed from project mirror"; \
        else \
          PYTHONPATH=/install/lib/python3.12/site-packages HF_HOME=/tmp/hfcache \
            python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2').save('/install/st-minilm'); CrossEncoder('cross-encoder/stsb-distilroberta-base').save('/install/st-ce')" \
          && echo "[nlp] ST/CE models baked from HuggingFace"; \
        fi \
     && chmod -R a+rX /install/st-minilm /install/st-ce \
     && rm -rf /tmp/hfcache /tmp/st-models \
    || echo "[nlp] MiniLM/cross-encoder not baked — evidence alignment degrades to TF-IDF"
# chmod a+rX after the bake is LOAD-BEARING: huggingface-hub 0.36's hf-xet
# download path writes model.safetensors 0600 (root-only) and .save()
# preserves that mode. The runtime stage runs as USER app, so without the
# chmod the CrossEncoder/MiniLM load raises EACCES → rerank.available()
# False → live-pg model-tier tests skip → no-skips gate fails the build
# (build 7cee4776, 2026-07-10 — verified against the pulled image).
# Two-tier evidence↔capability alignment (app/services/nlp/{semantic,rerank}.py):
#   • bi-encoder all-MiniLM (/install/st-minilm) = recall;
#   • cross-encoder stsb-distilroberta (/install/st-ce) = precision + calibrated
#     support — reads each (capability, evidence) pair jointly so word-overlap
#     decoys collapse to ~0 and true support calibrates toward ~0.95 (vs the
#     bi-encoder's ~0.5 plateau). RoBERTa BPE → round-trips offline cleanly.
# NOTE: this list is hand-maintained and must stay in lock-step with the
# core `dependencies` in backend/pyproject.toml. `jinja2` powers the B-6
# prospecting HTML scorecard export (app/services/scorecard_export.py),
# which is imported at app startup via the prospecting router — omitting it
# crashes the container on boot. `weasyprint` powers the PDF scorecard export
# (render_scorecard_pdf): the "Export PDF" button used to 501 because the
# package was absent (2026-07-07 deploy review — AE reported the scorecard was
# not downloadable). Its native deps (libpango / libcairo / libgdk-pixbuf /
# libffi) are installed in the RUNTIME stage below where weasyprint dlopen()s
# them at import time. pydyf is pinned alongside it: weasyprint's own `pydyf>=…`
# floor is too loose — 62.3 silently resolved pydyf 0.12.1 whose API it predates,
# so write_pdf() raised AttributeError at RUNTIME while the build stayed green
# (2026-07-07 validation). 63.1 + pydyf 0.12.1 is the verified-rendering pair.

# ── runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PORT=8000 \
    PATH="/install/bin:$PATH" \
    PYTHONPATH="/install/lib/python3.12/site-packages" \
    DMA_ST_MODEL_DIR="/install/st-minilm" \
    DMA_CE_MODEL_DIR="/install/st-ce" \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false

# Runtime deps:
#   libpq5 / libxml2 / libxslt1.1 — base Python C extensions
#   tesseract-ocr / poppler-utils — OCR fallback for retry-mode deep
#     extraction (`app.services.parsers.deep_extract`). The
#     historical_backfill Cloud Run Job uses the BACKEND image (not
#     workers), so when an operator clicks "Run retries (failed only)"
#     and the parser ladder reaches the OCR strategy, pytesseract +
#     pdf2image need the system binaries here -- without them the OCR
#     branch raises and deep_extract silently returns ("", 0).
# WeasyPrint (PDF scorecard export) dlopen()s Pango/Cairo/GDK-PixBuf/FFI at
# import time — install the shared libs + a base font (fonts-liberation) so
# render_scorecard_pdf produces a real file instead of ImportError → 501.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 libxml2 libxslt1.1 \
        tesseract-ocr poppler-utils \
        libpango-1.0-0 libpangocairo-1.0-0 libcairo2 \
        libgdk-pixbuf-2.0-0 libffi8 fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash app

COPY --from=builder /install /install
COPY backend/app /home/app/app
COPY backend/alembic /home/app/alembic
COPY backend/alembic.ini /home/app/alembic.ini

# Include the workers package so the API can import shared utilities
# (e.g. catalogue dispatch tables); the worker container has its own
# entrypoint and runs the Cloud Run Jobs.
COPY workers /home/app/workers

# v7.0 catalogue workbooks (~17 MB) — lets the deploy-refresh phase run
# `app.scripts.apply_catalogue_platforms` in-cluster (the subcap->platform
# L3 supplement) without a GCS round-trip. Same bake-the-data precedent
# as the corpus COPY below.
COPY docs/reference/catalogue/v7.0 /home/app/docs/reference/catalogue/v7.0

# Ship the pre-generated CI fixtures (5 sanitized DMA packages, ~400 KB
# total) so `python -m app.scripts.seed_ci` works inside the image.
# The script resolves the fixture root via parents[2] → /home/app/tests/
# fixtures/dma_packages_sanitized. We bundle only the DATA dirs — the
# dev-only generator (generate_fixtures.py) is intentionally NOT shipped,
# so seed_ci.py was refactored to not import it at runtime.
# Failure mode if missing: seed_ci hard-fails with an actionable error
# (RuntimeError pointing at this Dockerfile) instead of the previous
# ModuleNotFoundError trying to reach tests.fixtures.* at runtime.
COPY backend/tests/fixtures/dma_packages_sanitized/regions      /home/app/tests/fixtures/dma_packages_sanitized/regions
COPY backend/tests/fixtures/dma_packages_sanitized/amalgamated  /home/app/tests/fixtures/dma_packages_sanitized/amalgamated
COPY backend/tests/fixtures/dma_packages_sanitized/anb          /home/app/tests/fixtures/dma_packages_sanitized/anb
COPY backend/tests/fixtures/dma_packages_sanitized/wsfs         /home/app/tests/fixtures/dma_packages_sanitized/wsfs
COPY backend/tests/fixtures/dma_packages_sanitized/americu      /home/app/tests/fixtures/dma_packages_sanitized/americu
COPY backend/tests/fixtures/dma_packages_sanitized/richbank     /home/app/tests/fixtures/dma_packages_sanitized/richbank

# Ship the 113-package corpus (~244 MB) so the historical_backfill
# Cloud Run Job can seed the live DB at deploy time when
# DMA_SEED_CORPUS_ON_DEPLOY=1 is set (post-deploy-refresh.sh
# --seed-corpus). The intelligent material_manifest_hash skip
# (migration 033) makes re-deploys near-no-op: only NEW or materially
# changed packages cost any work on subsequent deploys.
#
# Operator decision per the 2026-06-07 mandate "Ensure the 100+ DMAs
# are loaded onto the DB and persisted during deployment." This adds
# ~250 MB to the runtime image; in trade we get deploy-time data
# hydration without any GCS-bucket / sidecar infrastructure. To opt
# out for a leaner production-only image, comment the COPY below and
# rely on the drive_crawler Cloud Scheduler probes (6h delta + 02:00
# daily NEW-folder discovery via the dma-insights-drive-crawler-
# daily-discovery scheduler). The historical_backfill --dir path
# still works as a manual command for ad-hoc seeding.
#
# Future migration: move the corpus to a GCS bucket + bind-mount in
# the historical_backfill Job, keeping the runtime image lean.
COPY backend/tests/fixtures/dma_packages_batches /home/app/tests/fixtures/dma_packages_batches

# Ship the committed startup-data snapshot (~0.9 MB) so the deploy-refresh
# phase can run `app.scripts.export_startup_data --check` in-cluster: the
# committed first-paint payload's STRUCTURE is verified against the freshly
# derived DB on every deploy (post-deploy-refresh.sh §2c). The exporter is
# invoked there with an explicit --out /home/app/startup-data.
COPY startup-data /home/app/startup-data

WORKDIR /home/app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=3).getcode() == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
