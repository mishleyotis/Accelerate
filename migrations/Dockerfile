# svc_migrate — Cloud Run Job, pre-deploy. Runs Alembic and exits; the
# deploy proceeds only on success (TRD deployment mapping).
FROM python:3.12-slim
WORKDIR /migrations
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["alembic", "upgrade", "head"]
