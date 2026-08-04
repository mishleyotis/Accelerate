FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
# Bundle the embedding model in-image: no network at submit, deterministic
# output, pinned name (TRD §18 — model pinning).
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2').save('/model')"
ENV EMBED_MODEL_DIR=/model PORT=8080
COPY dma_mcp ./dma_mcp
COPY server.py .
CMD ["python", "server.py"]
