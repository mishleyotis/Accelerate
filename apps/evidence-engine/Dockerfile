# dmai-evidence — the evidence engine. Models are baked in at build; nothing
# is downloaded at request time (invariant 1: no model call on a serving
# path; here the models are deterministic local rankers, bundled).
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Bake the ranking models (Apache-2.0 / MIT, chosen on the golden set —
# docs/EVAL-REPORT.md). EE_MODELS_DIR is what rank.py reads; absent, the
# engine runs BM25-only and says so in every result's `rerank` field.
ENV EE_MODELS_DIR=/models
RUN python -c "from fastembed import TextEmbedding; from fastembed.rerank.cross_encoder import TextCrossEncoder; \
    TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/models'); \
    TextCrossEncoder('Xenova/ms-marco-MiniLM-L-6-v2', cache_dir='/models')"
COPY registry ./registry
COPY evidence_engine ./evidence_engine
COPY evidence_server.py .
ENV PORT=8080 EE_DATA_DIR=/tmp/evidence-engine EDGAR_LOCAL_DATA_DIR=/tmp/evidence-engine/edgar
CMD ["python", "evidence_server.py"]
