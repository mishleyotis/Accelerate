"""Regression: post-deploy-refresh.sh CHAIN must reference Cloud Run Jobs
that actually exist in terraform.

The bug shape this guards against:

    # infra/post-deploy-refresh.sh
    CHAIN=(
      "dma-insights-drive-crawler-6h"              # ← scheduler name, NOT job name
      "dma-insights-embedder-hourly"               # ← scheduler name, NOT job name
      "dma-insights-intelligence-recompute-hourly" # ← scheduler name, NOT job name
    )

The script's lookup is fail-soft (`gcloud run jobs describe … || skipping`),
so a typo'd name silently falls through the "not registered; skipping"
branch and the entire delta-backfill chain becomes a no-op. Operators
then see exactly the symptom that motivated the script: "I still see the
logs picking wrong evidence and subcap counts ... a new deployment
should always refresh everything."

Two name families live in terraform:
  - google_cloud_run_v2_job              ← the actual Cloud Run Jobs
    Names: dma-insights-${replace(local.jobs.<key>, "_", "-")} +
           explicit names like "dma-insights-migrations".
  - google_cloud_scheduler_job          ← the cron triggers; POST to
    https://…/jobs/<bare-name>:run. Names suffixed with cadence
    (`-6h`, `-hourly`, `-nightly`, `-weekly`).

`gcloud run jobs execute` resolves the FIRST family; the second won't
match. This test parses both and confirms every CHAIN entry is a
google_cloud_run_v2_job name.
"""
from __future__ import annotations

import re
from pathlib import Path


def _find_infra_dir() -> Path:
    """Locate apps/dma-insights/infra by walking up from this file.
    parents[N] is fragile under CI runners that mount the repo at
    arbitrary depth -- walk up until we find a directory containing
    a recognisable `infra/terraform/main.tf` marker."""
    here = Path(__file__).resolve()
    for ancestor in [here.parent, *here.parents]:
        candidate = ancestor / "infra" / "terraform" / "main.tf"
        if candidate.exists():
            return candidate.parent.parent  # → infra/
        # Also try the canonical apps/dma-insights layout.
        canonical = ancestor / "apps" / "dma-insights" / "infra" / "terraform" / "main.tf"
        if canonical.exists():
            return canonical.parent.parent  # → apps/dma-insights/infra/
    raise RuntimeError(
        f"could not locate infra/terraform/main.tf walking up from {here}"
    )


INFRA = _find_infra_dir()
TF_MAIN = INFRA / "terraform" / "main.tf"
REFRESH_SCRIPT = INFRA / "post-deploy-refresh.sh"


def _extract_terraform_run_job_names() -> set[str]:
    """Pull every Cloud Run Job name from main.tf.

    Two paths to a name:
      1. Literal `name = "dma-insights-…"` inside a
         `google_cloud_run_v2_job "x"` block.
      2. A `for_each = local.jobs` resource whose `name =
         "dma-insights-${replace(each.key, "_", "-")}"` — names come
         from the keys of `locals { jobs = { … } }`.

    The Cloud Scheduler family (`google_cloud_scheduler_job`) is
    intentionally excluded — those names target Cloud Run Jobs via
    `/jobs/<bare-name>:run` URIs but are NOT themselves Jobs.
    """
    text = TF_MAIN.read_text()
    names: set[str] = set()

    for block in re.finditer(
        r'resource\s+"google_cloud_run_v2_job"\s+"[^"]+"\s*\{(?P<body>(?:.|\n)*?)^\}',
        text,
        flags=re.MULTILINE,
    ):
        body = block.group("body")
        # The resource's own `name = …` lives at the top of the block
        # (depth 0). Env blocks have `name = "DATABASE_URL"` at depth 2
        # and we don't want those — restrict to literals that start with
        # `dma-insights-`. Cloud Run Job names always do.
        for m in re.finditer(r'^\s*name\s*=\s*"(dma-insights-[^"]+)"',
                             body, flags=re.MULTILINE):
            literal = m.group(1)
            if "${" not in literal:
                names.add(literal)
        if re.search(r"for_each\s*=\s*local\.jobs\b", body) and "replace(each.key" in body:
            for key in _extract_local_jobs_keys(text):
                names.add(f"dma-insights-{key.replace('_', '-')}")

    return names


def _extract_local_jobs_keys(text: str) -> list[str]:
    """Pull the top-level keys from `locals { jobs = { <key> = {...} } }`.
    Brace-balanced so it tolerates comments between `locals {` and `jobs =`
    AND the per-job object values (2026-06 cost safeguard: each job is
    `name = { args = [...], timeout = ..., max_retries = ... }`). Each job key
    is the only `<key> = {` at the map's top level (object fields use `= [`,
    `= "`, `= N`)."""
    start = text.find("jobs = {")
    if start == -1:
        return []
    open_idx = text.index("{", start)
    depth = 0
    body = ""
    for j in range(open_idx, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                body = text[open_idx + 1:j]
                break
    return re.findall(r"^\s+([a-z_][a-z0-9_]*)\s*=\s*\{", body, flags=re.MULTILINE)


def _extract_chain_from_refresh_script() -> list[str]:
    """Parse the literal CHAIN=( "..." "..." ) array from the script."""
    text = REFRESH_SCRIPT.read_text()
    m = re.search(r'CHAIN=\(\s*((?:.|\n)*?)\)', text)
    assert m, "could not locate CHAIN=( … ) in post-deploy-refresh.sh"
    body = m.group(1)
    quoted: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        quoted.extend(re.findall(r'"([^"]+)"', stripped))
    return quoted


def test_local_jobs_keys_are_discoverable() -> None:
    """Pre-check: the parser must find the local.jobs keys, otherwise the
    main assertion silently passes against an empty set."""
    keys = _extract_local_jobs_keys(TF_MAIN.read_text())
    assert "drive_crawler" in keys
    assert "embedder" in keys
    assert "intelligence_recompute" in keys


def test_post_deploy_refresh_chain_names_exist_in_terraform() -> None:
    """Every job name in CHAIN must be declared by a
    google_cloud_run_v2_job resource in terraform/main.tf — otherwise
    `gcloud run jobs describe` returns 'not registered' and the script
    silently skips the job."""
    chain = _extract_chain_from_refresh_script()
    assert chain, "CHAIN is empty — script never triggers backfill"
    tf_jobs = _extract_terraform_run_job_names()
    assert tf_jobs, "no google_cloud_run_v2_job names found in main.tf"
    missing = [job for job in chain if job not in tf_jobs]
    assert not missing, (
        f"post-deploy-refresh.sh CHAIN references job(s) that do not "
        f"exist as a google_cloud_run_v2_job in terraform: {missing}.\n"
        f"Declared jobs are: {sorted(tf_jobs)}.\n"
        f"(Common mistake: using the google_cloud_scheduler_job name — "
        f"those are NOT Cloud Run Jobs and can't be `gcloud run jobs "
        f"execute`d. The scheduler POSTs to the bare job name via "
        f"`/jobs/<name>:run`.)"
    )


def test_post_deploy_refresh_fires_ingest_and_runs_derive_chain() -> None:
    """New packages must not be left in PENDING after a deploy. The background
    ingest (drive_crawler + embedder) fires async, and intelligence_recompute
    + every derive now run inside run_derive_chain.

    2026-06-18: intelligence_recompute moved OUT of the (blocking) CHAIN — where
    it hung the deploy — and INTO run_derive_chain (wave 7); the crawler/embedder
    fire `--async` so they can't block the deterministic chain."""
    script = REFRESH_SCRIPT.read_text()
    chain = _extract_chain_from_refresh_script()
    for name in ("dma-insights-drive-crawler", "dma-insights-embedder"):
        assert name in chain, (
            f"post-deploy-refresh.sh CHAIN missing required worker '{name}'."
        )
    # intelligence_recompute is no longer a standalone blocking CHAIN exec; it
    # runs inside run_derive_chain, which the script dispatches via
    # DMA_POST_DEPLOY_RUN (--update-env-vars, not a --command override).
    assert "DMA_POST_DEPLOY_RUN=derive_chain" in script, (
        "post-deploy-refresh.sh must dispatch run_derive_chain (it carries "
        "intelligence_recompute + every derive step)."
    )
    # And the background ingest must be non-blocking.
    assert "--async" in script, "background ingest (CHAIN) must be fired --async"


def test_post_deploy_refresh_runs_derive_chain_for_surfaces() -> None:
    """2026-06-10 census: derive modules existed but never ran on deploy, so
    platform tags / peer medians / alerts were empty corpus-wide. The fix ran
    them all on deploy.

    2026-06-18: they now run as ONE `run_derive_chain` execution (parallel
    waves, per-step timeout) instead of 21 fragile separate `--wait` execs that
    ALL failed on the 2026-06-18 deploy. The module SET + dependency ORDER are
    locked to run_derive_chain by test_derive_chain_contract.py
    (run_derive_chain.STEPS/WAVES) — here we just assert the script delegates to
    it and still runs the startup-data parity gate afterwards."""
    root = Path(__file__).resolve().parents[2]
    script = (root / "infra" / "post-deploy-refresh.sh").read_text(encoding="utf-8")
    # 2026-06-18: dispatched via DMA_POST_DEPLOY_RUN (--update-env-vars), not a
    # --command override (which silently failed on `gcloud run jobs execute`).
    assert "DMA_POST_DEPLOY_RUN=derive_chain" in script, (
        "post-deploy-refresh.sh no longer dispatches run_derive_chain — the "
        "derived surfaces (platform tags, peer medians, alerts, insights, focus "
        "areas, …) will render empty on a fresh deploy."
    )
    # The structural parity gate must still run AFTER the chain (same dispatch).
    assert "DMA_POST_DEPLOY_RUN=export_check" in script, (
        "post-deploy-refresh.sh must still run export_startup_data --check after "
        "the derive chain to catch startup-data structural drift."
    )
    # The signal→module routing lives in historical_backfill's entrypoint.
    hb = (root / "backend" / "app" / "scripts" / "historical_backfill.py").read_text()
    assert '"derive_chain": ("app.scripts.run_derive_chain"' in hb
