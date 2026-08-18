# The two corpus Jobs — pack-exporter and corpus-gate-scanner — in one image.
# They share the pack's shape, so shipping them apart would mean two copies of
# it, free to drift. The Job's `--command`/`--args` chooses which one runs.
#
# `corpus_gates.json` is copied into the build context by infra/deploy.sh from
# packages/shared/, which is the single source of the ceilings (CI Gate B
# ratchets that file, not this copy).
FROM python:3.12-slim
WORKDIR /jobs
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "corpus_jobs.pack_export"]
