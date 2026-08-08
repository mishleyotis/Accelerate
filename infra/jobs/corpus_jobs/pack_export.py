"""`pack-exporter` — the second of the charter's three mandatory Scheduler
triggers (nightly, and on demand).

    python -m corpus_jobs.pack_export [--dry-run]

Writes two objects to `gs://<project>-dmai-corpus-packs`:

    packs/<UTC date>/corpus-pack-<UTC timestamp>.json   the dated pack
    packs/latest.json                                    a copy, so the
                                                         scanner has one
                                                         name to read

The dated object is the record and is never overwritten; `latest.json` is a
pointer that is. Both are written, in that order — a scanner that read
`latest.json` while the dated write was still in flight would measure a
corpus that was never exported.

Identity: `dmai-mcp`. It is the only service account that already holds both
halves of this job's needs — SELECT across the serving tier (svc_mcp) and,
with the binding provision.sh adds, object access on the pack bucket. Running
it as `dmai-api` would mean granting the serving API's identity write access
to a bucket the service never uses; running it as `dmai-worker` would mean
granting the ingest identity read access to the serving tier it is
deliberately denied.

Not built here: the scorecard PDF. It needs headless Chromium in the image
and a rendered page to shoot, and belongs with the surface whose layout it
captures. This Job says so in its log rather than shipping an empty file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from .db import close, connect
from .pack import build_pack, pack_bytes

BUCKET = os.environ.get(
    "PACK_BUCKET",
    f"{os.environ.get('GCP_PROJECT', 'digital-maturity-assessor')}-dmai-corpus-packs")


def _upload(bucket_name: str, path: str, data: bytes) -> str:
    from google.cloud import storage
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(path)
    blob.upload_from_string(data, content_type="application/json")
    return f"gs://{bucket_name}/{path}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="corpus_jobs.pack_export")
    p.add_argument("--dry-run", action="store_true",
                   help="build and report the pack; write no object")
    p.add_argument("--bucket", default=BUCKET)
    args = p.parse_args(argv)

    now = datetime.now(timezone.utc)
    conn = connect()
    try:
        pack = build_pack(conn.cursor(), as_of=now)
    finally:
        conn.close()
        close()

    data = pack_bytes(pack)
    counts = pack["counts"]
    print(f"pack-exporter: {counts['clients']} client(s), {counts['cells']} "
          f"served cells, {counts['pages_promoted']} of "
          f"{counts['pages_expected']} pages promoted, {len(data)} bytes",
          flush=True)
    for c in pack["clients"]:
        print(f"  {c['display_id']}: run {c['request_id']} "
              f"pages={c['pages_promoted']}/{c['pages_expected']} "
              f"cells={c['cells']} thin={c['cells_thin_evidence']} "
              f"date_basis={c['assessment_date_basis']} "
              f"overdue={c['refresh_overdue']}", flush=True)

    if args.dry_run:
        print("pack-exporter: --dry-run, nothing written", flush=True)
        return 0

    if counts["clients"] == 0:
        # An empty corpus is a real state, not a failure — but overwriting
        # `latest.json` with nothing would make every subsequent gate read
        # zero and pass. Absent beats wrong: the dated object records the
        # emptiness, the pointer is left alone.
        dated = _upload(args.bucket,
                        f"packs/{now:%Y-%m-%d}/corpus-pack-{now:%Y%m%dT%H%M%SZ}.json",
                        data)
        print(f"pack-exporter: wrote {dated}; latest.json left untouched "
              "because the corpus is empty and a zero pack would make every "
              "ceiling pass", flush=True)
        return 0

    dated = _upload(args.bucket,
                    f"packs/{now:%Y-%m-%d}/corpus-pack-{now:%Y%m%dT%H%M%SZ}.json",
                    data)
    print(f"pack-exporter: wrote {dated}", flush=True)
    latest = _upload(args.bucket, "packs/latest.json", data)
    print(f"pack-exporter: wrote {latest}", flush=True)
    print("pack-exporter: the scorecard PDF is NOT built by this Job — it "
          "needs headless Chromium and the rendered surface, and ships with "
          "the export stage that owns that layout", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
