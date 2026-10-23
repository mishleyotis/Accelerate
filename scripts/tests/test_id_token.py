"""Smoke probes mint their Cloud Run ID token through infra/lib/id_token.sh.

2026-10-11, the de59ebe release: under CI's Workload Identity Federation
credential `gcloud auth print-identity-token --audiences=URL` printed
nothing. deploy.sh's api smoke read "NOT PROBED — no api URL or no identity
token for this account", and smoke.sh, which made the same call under
`set -e`, would have died on its first probe once the four evidence services
were up. The helper tries the active credential, then impersonates the
deployer service account. A probe it cannot run is NOT PROBED with the
reason, and fails the evidence smoke. Driven through a fake gcloud and curl.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "infra" / "lib" / "id_token.sh"
SMOKE = ROOT / "infra" / "evidence-engine" / "smoke.sh"

FAKE_GCLOUD = r'''#!/usr/bin/env bash
echo "$*" >> "$STATE/gcloud"
case "$*" in
  *"auth print-identity-token"*"--impersonate-service-account"*)
    [ -f "$STATE/imp_ok" ] && { echo "TOKEN-IMP"; exit 0; }
    echo "ERROR: (gcloud.auth.print-identity-token) PERMISSION_DENIED: iam.serviceAccounts.getOpenIdToken" >&2; exit 1 ;;
  *"auth print-identity-token"*)
    [ -f "$STATE/direct_ok" ] && { echo "TOKEN-DIRECT"; exit 0; }
    echo "WARNING: \`--scopes\` flag may not work as expected" >&2
    echo "ERROR: (gcloud.auth.print-identity-token) Invalid account type for \`--audiences\`. Requires valid service account." >&2; exit 1 ;;
  *"config get-value account"*) echo "deployer@p.iam.gserviceaccount.com" ;;
  *"run services describe"*) echo "https://svc.example.run.app" ;;
  *"secrets versions access"*) echo "door-segment" ;;
  *) exit 0 ;;
esac
'''

# wrong path -> 404; initialize -> no session header; tools/list -> one tool
FAKE_CURL = r'''#!/usr/bin/env bash
echo "$*" >> "$STATE/curl"
case "$*" in
  *"-w %{http_code}"*) printf 404 ;;
  *" -D - "*) : ;;
  *) echo 'data: {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"t"}]}}' ;;
esac
'''


def _env(tmp_path, *flags, deployer=None):
    bin_dir = tmp_path / "bin"; bin_dir.mkdir(exist_ok=True)
    state = tmp_path / "state"; state.mkdir(exist_ok=True)
    for name, body in (("gcloud", FAKE_GCLOUD), ("curl", FAKE_CURL)):
        (bin_dir / name).write_text(body); (bin_dir / name).chmod(0o755)
    for f in flags:
        (state / f).touch()
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", STATE=str(state))
    env.pop("GCP_DEPLOYER_SA", None)
    if deployer:
        env["GCP_DEPLOYER_SA"] = deployer
    return env, state


def _mint(env):
    script = f'. "{LIB}"; if id_token_into T "https://svc.example.run.app"; then echo "OK:$T"; else echo "NO:$ID_TOKEN_WHY"; fi'
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=30)


def test_the_active_credential_is_used_when_it_can_mint(tmp_path):
    env, state = _env(tmp_path, "direct_ok")
    r = _mint(env)
    assert r.stdout.strip() == "OK:TOKEN-DIRECT"
    assert "--impersonate-service-account" not in (state / "gcloud").read_text()


def test_a_wif_credential_falls_back_to_impersonating_the_deployer(tmp_path):
    env, state = _env(tmp_path, "imp_ok", deployer="claude-deployer@p.iam.gserviceaccount.com")
    r = _mint(env)
    assert r.stdout.strip() == "OK:TOKEN-IMP"
    calls = (state / "gcloud").read_text()
    assert "--impersonate-service-account=claude-deployer@p.iam.gserviceaccount.com" in calls
    assert "--audiences=https://svc.example.run.app" in calls
    # without the env var it impersonates the active account
    (state / "gcloud").unlink()
    env2, _ = _env(tmp_path, "imp_ok")
    assert _mint(env2).stdout.strip() == "OK:TOKEN-IMP"
    assert "--impersonate-service-account=deployer@p.iam.gserviceaccount.com" in (state / "gcloud").read_text()


def test_no_route_returns_1_with_both_reasons_and_no_token(tmp_path):
    env, _ = _env(tmp_path, deployer="claude-deployer@p.iam.gserviceaccount.com")
    r = _mint(env)
    out = r.stdout.strip()
    assert out.startswith("NO:active credential: ERROR") and "Invalid account type" in out
    assert "impersonating claude-deployer@p.iam.gserviceaccount.com: ERROR" in out and "getOpenIdToken" in out
    assert "WARNING" not in out, "the reason is the error line, not a gcloud warning"
    assert "TOKEN" not in r.stdout + r.stderr


def test_smoke_reports_not_probed_and_fails_when_no_token_can_be_minted(tmp_path):
    env, state = _env(tmp_path, deployer="claude-deployer@p.iam.gserviceaccount.com")
    r = subprocess.run(["bash", str(SMOKE)], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 1, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("NOT PROBED")]
    assert [ln.split()[2].rstrip(":") for ln in lines] == ["dmai-evidence", "dmai-searxng", "dmai-fetch", "dmai-edgar"]
    assert "PASS" not in r.stdout
    assert not (state / "curl").exists(), "no door is called without a token"


def test_smoke_probes_every_door_with_the_impersonated_token(tmp_path):
    env, state = _env(tmp_path, "imp_ok", deployer="claude-deployer@p.iam.gserviceaccount.com")
    r = subprocess.run(["bash", str(SMOKE)], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.count("PASS") == 8 and "NOT PROBED" not in r.stdout
    curls = (state / "curl").read_text()
    assert "Authorization: Bearer TOKEN-IMP" in curls
    assert "TOKEN-IMP" not in r.stdout + r.stderr, "the token is never printed"


def test_both_smokes_mint_through_the_helper():
    deploy = (ROOT / "infra" / "deploy.sh").read_text()
    smoke = SMOKE.read_text()
    for src in (deploy, smoke):
        assert "lib/id_token.sh" in src and "id_token_into " in src
    assert "auth print-identity-token" not in smoke
    i = deploy.index('say "smoke: does the api still reach the database?"')
    assert "auth print-identity-token" not in deploy[i:i + 2500]
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    step = ci[ci.index("- name: infra/deploy.sh"):][:400]
    assert "GCP_DEPLOYER_SA: ${{ vars.GCP_DEPLOYER_SA }}" in step


def test_the_owner_grant_lets_the_deployer_mint_its_own_id_token():
    """2019ffb release (2026-10-11): impersonating claude-deployer for an ID
    token read IAM_PERMISSION_DENIED, so every smoke was NOT PROBED. The
    owner's one-time grant gives exactly that permission, on the deployer
    service account itself, never project-wide."""
    src = (ROOT / "infra" / "grants-for-admin.sh").read_text()
    i = src.index("roles/iam.serviceAccountOpenIdTokenCreator")
    stmt = src[src.rindex("gcloud ", 0, i):i]
    assert stmt.startswith("gcloud iam service-accounts add-iam-policy-binding"), stmt
    assert '"${DEPLOYER#serviceAccount:}"' in stmt and '--member="$DEPLOYER"' in stmt
    assert src.count("serviceAccountOpenIdTokenCreator") == 2, "one grant and its echo; no project-level copy"
    r = subprocess.run(["bash", "-n", str(ROOT / "infra" / "grants-for-admin.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
