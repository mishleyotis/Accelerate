#!/usr/bin/env python3
"""Is what is committed actually what production is serving?

THE FAILURE THIS ENDS, which happened twice and was reported both times by the
build owner rather than caught here:

  1. Four render fixes were reported as live. The deployed web revision had been
     built 58 minutes BEFORE they were committed.
  2. Three commits — the enrichment gap, the duplicate-CAGR fix, the whole
     resilience layer — sat behind a deploy that had completed earlier. "Why am
     I not getting the changes redeployed? I still see the same thing I have
     been seeing."

Both times the deploy script exited 0 and every test passed. Neither is a build
failure; both are a TIME failure — code committed after the last build. Nothing
in this repo compared the two, so the only check was memory, and memory reported
success.

WHAT THIS DOES, and why it is stronger than comparing timestamps: it pulls the
DEPLOYED image out of Artifact Registry by digest, extracts the compiled bundle
the browser downloads, and hashes it against a local build of HEAD. A timestamp
comparison tells you a build happened after a commit; this tells you the bytes
match. It is the check that found the enrichment flag rendering on one surface
of five, and it is the only verification available while the web service sits
behind IAP and cannot be loaded by this build's identity (MEM-0065).

    verify_deployed.py                 # all services, bundle compared
    verify_deployed.py --quick         # revisions and build times only

Exit 0 when the deployed bundle matches HEAD, 1 when it does not, 2 when the
comparison could not be made — which is NOT a pass, and says so.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = os.environ.get("GCP_PROJECT", "digital-maturity-assessor")
REGION = os.environ.get("GCP_REGION", "us-central1")
SERVICES = ("dmai-web", "dmai-api", "dmai-mcp")
BUNDLE_IN_IMAGE = "app/public/proto/js/"
BUNDLE_LOCAL = ROOT / "apps" / "web" / "public" / "proto" / "js"

GCLOUD = shutil.which("gcloud") or "/root/google-cloud-sdk/bin/gcloud"


def sh(args: list) -> str:
    env = dict(os.environ)
    # A stale access token in the environment silently outranks the active
    # service account and every call then reports the wrong project's state.
    env.pop("CLOUDSDK_AUTH_ACCESS_TOKEN", None)
    r = subprocess.run(args, capture_output=True, text=True, env=env, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:400])
    return r.stdout.strip()


def head_commit() -> tuple:
    return (sh(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"]),
            sh(["git", "-C", str(ROOT), "log", "-1", "--format=%cI"]))


def deployed(service: str) -> dict:
    rev = sh([GCLOUD, "run", "services", "describe", service,
              "--project", PROJECT, "--region", REGION,
              "--format", "value(status.latestReadyRevisionName)"])
    meta = sh([GCLOUD, "run", "revisions", "describe", rev,
               "--project", PROJECT, "--region", REGION,
               "--format", "value(metadata.creationTimestamp,status.imageDigest)"])
    parts = meta.split("\t") if "\t" in meta else meta.split()
    return {"service": service, "revision": rev,
            "built_at": parts[0] if parts else "",
            "image": parts[1] if len(parts) > 1 else ""}


def _digests(image_ref: str) -> list:
    """Layer digests of the deployed image, newest last."""
    host, _, rest = image_ref.partition("/")
    repo, _, digest = rest.partition("@")
    token = sh([GCLOUD, "auth", "print-access-token"])
    url = f"https://{host}/v2/{repo}/manifests/{digest}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.docker.distribution.manifest.v2+json,"
                             "application/vnd.oci.image.manifest.v1+json")
    with urllib.request.urlopen(req, timeout=120) as r:
        man = json.loads(r.read())
    return [(l["digest"], l.get("size", 0), host, repo, token)
            for l in man.get("layers", [])]


def deployed_bundle(image_ref: str) -> dict:
    """{filename: sha256} for the compiled bundle inside the DEPLOYED image."""
    out: dict = {}
    layers = _digests(image_ref)
    # Newest layers first: the app layer is near the top and usually small.
    for digest, _size, host, repo, token in sorted(layers, key=lambda l: l[1]):
        url = f"https://{host}/v2/{repo}/blobs/{digest}"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        with tempfile.NamedTemporaryFile(suffix=".tgz", delete=False) as fh:
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    shutil.copyfileobj(r, fh)
            except Exception:
                continue
            tmp = fh.name
        try:
            with tarfile.open(tmp, "r:gz") as t:
                for m in t.getmembers():
                    if m.name.startswith(BUNDLE_IN_IMAGE) and m.name.endswith(".js"):
                        f = t.extractfile(m)
                        if f:
                            out[m.name.rsplit("/", 1)[-1]] = hashlib.sha256(
                                f.read()).hexdigest()
        except Exception:
            pass
        finally:
            os.unlink(tmp)
        if out:
            break
    return out


def local_bundle() -> dict:
    if not BUNDLE_LOCAL.exists():
        return {}
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(BUNDLE_LOCAL.glob("*.js"))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="revisions and build times only; no image pull")
    a = ap.parse_args()

    commit, when = head_commit()
    print(f"HEAD {commit} committed {when}\n")

    rows = []
    for svc in SERVICES:
        try:
            rows.append(deployed(svc))
        except Exception as e:
            print(f"  {svc:10} COULD NOT READ — {e}")
            rows.append({"service": svc, "revision": "?", "built_at": "",
                         "image": ""})
    for r in rows:
        stale = r["built_at"] and r["built_at"] < when
        flag = "  <-- BUILT BEFORE HEAD" if stale else ""
        print(f"  {r['service']:10} {r['revision']:24} built {r['built_at']}{flag}")

    behind = [r for r in rows if r["built_at"] and r["built_at"] < when]
    if a.quick:
        if behind:
            print(f"\n{len(behind)} service(s) were built before HEAD was "
                  "committed. Whatever HEAD changed is NOT what production "
                  "serves. Run infra/deploy.sh.")
            return 1
        print("\nEvery service was built after HEAD. Run without --quick to "
              "compare the bundle bytes.")
        return 0

    web = next((r for r in rows if r["service"] == "dmai-web"), None)
    if not web or not web.get("image"):
        print("\nCould not read the web image digest — comparison NOT made. "
              "That is not a pass.")
        return 2
    local = local_bundle()
    if not local:
        print("\nNo local compiled bundle. Run `npm run build:proto` in "
              "apps/web first — comparison NOT made.")
        return 2
    try:
        remote = deployed_bundle(web["image"])
    except Exception as e:
        print(f"\nCould not read the deployed bundle — {e}. Comparison NOT "
              "made. That is not a pass.")
        return 2
    if not remote:
        print("\nThe deployed image carries no compiled bundle at "
              f"{BUNDLE_IN_IMAGE} — comparison NOT made.")
        return 2

    differs = sorted(k for k in set(local) | set(remote)
                     if local.get(k) != remote.get(k))
    print(f"\nBundle: {len(remote)} module(s) in the deployed image, "
          f"{len(local)} built locally.")
    if not differs:
        print("MATCH — every compiled module in production is byte-identical "
              "to a local build of HEAD.")
        return 0
    print(f"DIFFERS on {len(differs)} module(s):")
    for k in differs:
        state = ("only local" if k not in remote else
                 "only deployed" if k not in local else "different bytes")
        print(f"    {k:38} {state}")
    print("\nProduction is not serving HEAD. Run infra/deploy.sh, wait for "
          "SCRIPT_EXIT=0, then re-run this.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
