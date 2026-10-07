"""infra/deploy.sh — the usage dataset grants, run against fake bq/gcloud.

The 2026-10-07 16:10 release created the dmai_usage dataset and the dmai-usage
sink, then warned twice: `bq add-iam-policy-binding` on the dataset was
refused, so the sink could not write and dmai-web could not read ("Usage data
is not readable" in production). The block now takes the dataset's access
list, falls back to a project binding conditioned to the dataset, and reads
the result back. Asserted here by executing the block itself:

1. access list accepted → WRITER for the sink, READER for dmai-web, no
   project binding;
2. access list refused → both land as conditional project bindings whose
   expression is scoped to this dataset;
3. both refused → each failure is a WARN, never a silent pass;
4. a second run writes nothing.
"""
import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = (ROOT / "infra" / "deploy.sh").read_text()

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

BQ = textwrap.dedent("""\
    #!/bin/bash
    echo "bq $*" >> "$STATE/calls"
    case " $* " in
      *" show "*) [ "${BQ_SHOW_NOT_JSON:-0}" = 1 ] && { echo "Welcome to BigQuery!"; exit 0; }
         cat "$STATE/acl.json" ;;
      *" update "*) [ "${BQ_UPDATE_FAIL:-0}" = 1 ] && exit 1
         src=$(echo "$*" | sed -E 's/.*--source ([^ ]+).*/\\1/'); cp "$src" "$STATE/acl.json" ;;
    esac
""")
GCLOUD = textwrap.dedent("""\
    #!/bin/bash
    echo "gcloud $*" >> "$STATE/calls"
    case "$*" in
      *get-iam-policy*)
         role=$(echo "$*" | sed -E 's/.*bindings.role=([^ ]+) AND.*/\\1/')
         mem=$(echo "$*" | sed -E 's/.*bindings.members=([^ ]+).*/\\1/')
         grep -qx "$role $mem" "$STATE/proj" 2>/dev/null && echo "$role" ;;
      *add-iam-policy-binding*)
         [ "${COND_FAIL:-0}" = 1 ] && exit 1
         role=$(echo "$*" | sed -E 's/.*--role=([^ ]+).*/\\1/')
         mem=$(echo "$*" | sed -E 's/.*--member=([^ ]+).*/\\1/')
         echo "$*" >> "$STATE/conditions"
         echo "$role $mem" >> "$STATE/proj" ;;
    esac
""")


def _block():
    start = DEPLOY.index('  USAGE_DS_RES="projects/')
    end = DEPLOY.index('  usage_ds_access READER "dmai-web@${SA_DOMAIN}"')
    end = DEPLOY.index("\n", DEPLOY.index("usage_warn", end)) + 1
    return DEPLOY[start:end]


def _run(tmp_path, **env):
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    for name, body in (("bq", BQ), ("gcloud", GCLOUD)):
        (bin_ / name).write_text(body)
        (bin_ / name).chmod(0o755)
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    if not (state / "acl.json").exists():
        (state / "acl.json").write_text(json.dumps({"id": "p:dmai_usage", "etag": "x", "access": [
            {"role": "OWNER", "userByEmail": "claude-deployer@p.iam.gserviceaccount.com"}]}))
    script = tmp_path / "block.sh"
    script.write_text("set -euo pipefail\n"
                      'say(){ echo "$*"; }\n'
                      'usage_warn(){ echo "WARN $*"; }\n'
                      'usage_try(){ "$@" >/dev/null 2>&1; }\n' + _block())
    e = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "STATE": str(state),
         "PROJECT_ID": "p", "USAGE_DATASET": "dmai_usage", "USAGE_SINK": "dmai-usage",
         "SA_DOMAIN": "p.iam.gserviceaccount.com", "USAGE_ATTEMPTS": "1",
         "SINK_WRITER": "serviceAccount:service-1@gcp-sa-logging.iam.gserviceaccount.com", **env}
    out = subprocess.run(["bash", str(script)], env=e, capture_output=True, text=True, timeout=60)
    acl = json.loads((state / "acl.json").read_text())["access"]
    proj = (state / "proj").read_text().split("\n") if (state / "proj").exists() else []
    return out.stdout + out.stderr, {(a["role"], a["userByEmail"]) for a in acl}, [p for p in proj if p], state


def test_access_list_route(tmp_path):
    log, acl, proj, _ = _run(tmp_path)
    assert ("WRITER", "service-1@gcp-sa-logging.iam.gserviceaccount.com") in acl
    assert ("READER", "dmai-web@p.iam.gserviceaccount.com") in acl
    assert proj == [] and "WARN" not in log


def test_conditional_binding_fallback_is_scoped_to_the_dataset(tmp_path):
    log, acl, proj, state = _run(tmp_path, BQ_UPDATE_FAIL="1")
    assert set(proj) == {
        "roles/bigquery.dataEditor serviceAccount:service-1@gcp-sa-logging.iam.gserviceaccount.com",
        "roles/bigquery.dataViewer serviceAccount:dmai-web@p.iam.gserviceaccount.com"}
    for line in (state / "conditions").read_text().splitlines():
        assert re.search(r'--condition=expression=resource\.name\.startsWith\("projects/p/datasets/dmai_usage"\)', line), line
    assert "WARN" not in log


def test_refusal_on_both_routes_warns(tmp_path):
    log, _, proj, _ = _run(tmp_path, BQ_UPDATE_FAIL="1", COND_FAIL="1")
    assert "WARN could not grant the sink writer dataEditor" in log
    assert "WARN could not grant dmai-web dataViewer" in log
    assert proj == []


def test_second_run_writes_nothing(tmp_path):
    _, _, _, state = _run(tmp_path)
    first = len((state / "calls").read_text().splitlines())
    log, _, _, state = _run(tmp_path)
    second = (state / "calls").read_text().splitlines()[first:]
    assert not any(" update " in c or "add-iam-policy-binding" in c for c in second), second
    assert "granting" not in log


def test_bigquery_api_is_read_before_it_is_enabled():
    i = DEPLOY.index("gcloud services enable bigquery.googleapis.com")
    assert "gcloud services list --enabled" in DEPLOY[i - 400:i]


def test_unreadable_show_output_falls_back_quietly(tmp_path):
    """The 18:13 UTC release: `bq show` exited 0 with no JSON. The block must
    fall through to the conditional binding without a Python traceback."""
    log, _, proj, _ = _run(tmp_path, BQ_SHOW_NOT_JSON="1")
    assert "Traceback" not in log, log
    assert "WARN" not in log
    assert len(proj) == 2


def test_format_is_a_global_flag():
    for line in DEPLOY.splitlines():
        if "bq " in line and "prettyjson" in line and " show" in line:
            assert line.index("--format=prettyjson") < line.index(" show"), line
