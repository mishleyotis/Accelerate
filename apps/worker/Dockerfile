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
COPY job_main.py .
CMD ["python", "job_main.py"]
