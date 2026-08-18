FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
# The embedding model bundles in-image (same pinned name as the connector
# — a mixed-model index returns plausible nonsense, TRD §18).
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2').save('/model')"
ENV EMBED_MODEL_DIR=/model
COPY dma_worker ./dma_worker
# Cross-service contracts the enrichment routine READS at runtime — the gap
# computation and the contract it reads against, shared with the connector so
# the two can never disagree about what is missing. Staged by deploy.sh, never
# committed here; Gate D fails CI if a file this code reads is not shipped.
COPY shared ./shared
COPY job_main.py .
CMD ["python", "job_main.py"]
