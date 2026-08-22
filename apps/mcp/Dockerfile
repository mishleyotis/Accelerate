FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
# Bundle the embedding model in-image: no network at submit, deterministic
# output, pinned name (TRD §18 — model pinning).
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2').save('/model')"
ENV EMBED_MODEL_DIR=/model PORT=8080
# The gap computation the connector shares with the worker's enrichment
# routine, plus the contract it reads against. dma_mcp/gaps.py imports
# `enrichment_gaps` at module load, so WITHOUT this the container dies on
# startup — which is exactly what deploy 8 did. Staged by deploy.sh.
COPY shared ./shared
COPY dma_mcp ./dma_mcp
COPY server.py .
CMD ["python", "server.py"]
