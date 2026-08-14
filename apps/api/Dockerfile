FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY dma_api ./dma_api
# Cross-service contracts the serving code READS at runtime. deploy.sh stages
# packages/shared/*.json in here before building, the same way it stages
# corpus_gates.json for the corpus jobs — so there is no second copy in the
# tree to drift out of step with the one CI checks.
#
# The directory is tracked with a .gitkeep so this COPY never fails on a bare
# `docker build apps/api`; a build that skipped the staging step gets an empty
# shared/ and the loader raises by name rather than serving as though nothing
# were declared. That silent-empty behaviour is what shipped the enrichment
# status missing on all five surfaces.
COPY shared ./shared
ENV PORT=8080
CMD ["sh", "-c", "uvicorn dma_api.main:app --host 0.0.0.0 --port ${PORT}"]
