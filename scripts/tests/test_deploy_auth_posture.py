"""The connector must not be deployed public, asserted where it is decided.

`infra/deploy.sh` passed `--allow-unauthenticated` for `dmai-mcp` until
2026-08-16. That flag grants roles/run.invoker to allUsers. The plugin minted
a Google identity token on every connection and sent it; nothing on the other
side read it, so authentication rested entirely on a 32-character path token
travelling in a URL — on the single component permitted to write serving
content, while `dmai-api` and `dmai-web` were correctly closed.

Two things had to be true for that to survive as long as it did, and this file
is about the second:

  1. no check measured ENFORCEMENT. Every check measured that a credential
     EXISTED — a token minted, an audience matched — and all of them passed.
  2. the posture lived in one line of a shell script that nothing read back.

Repairing the IAM policy by hand fixes (1)'s symptom for exactly as long as it
takes someone to run the next release. The flag is the source of truth, so the
assertion belongs on the flag.

This is a text test on purpose. It needs no GCP credentials, so it runs in CI
on every commit, which is where a reopened service has to be caught — not at
deploy time, when the argument for shipping anyway is strongest.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[2] / "infra" / "deploy.sh"

#: Services that must never be reachable without a Google identity, and why
#: each one matters. `dmai-web` is deliberately absent: it is the browser
#: entry point and is fronted by IAP, which does the authenticating.
CLOSED_SERVICES = {
    "dmai-mcp": "the only component permitted to write serving content",
    "dmai-api": "serves promoted client content, including internal audiences",
}


def _deploy_block(service: str) -> str:
    """The text of one `gcloud run deploy <service>` invocation.

    A deploy invocation is a single logical line split across many physical
    ones with backslashes; the block ends at the first line that does not
    continue. Scanning the whole file instead would let a flag on ANOTHER
    service satisfy the assertion for this one.
    """
    text = DEPLOY.read_text()
    start = text.find(f"gcloud run deploy {service}")
    assert start != -1, f"no `gcloud run deploy {service}` in {DEPLOY}"
    out = []
    for line in text[start:].splitlines():
        out.append(line)
        if not line.rstrip().endswith("\\"):
            break
    return "\n".join(out)


@pytest.mark.parametrize("service", sorted(CLOSED_SERVICES))
def test_THE_SERVICE_IS_NOT_DEPLOYED_PUBLIC(service):
    block = _deploy_block(service)
    # `--no-allow-unauthenticated` contains `--allow-unauthenticated` as a
    # substring, so match the flag on a word boundary or this passes on the
    # exact bug it exists to catch.
    public = re.search(r"(?<!-)(?<!no-)--allow-unauthenticated\b", block)
    assert not public, (
        f"{service} is deployed with --allow-unauthenticated, which grants "
        f"roles/run.invoker to allUsers. {CLOSED_SERVICES[service]}. "
        "Use --no-allow-unauthenticated and grant the specific principals "
        "that must invoke it.")
    assert "--no-allow-unauthenticated" in block, (
        f"{service} states neither --allow-unauthenticated nor "
        "--no-allow-unauthenticated. gcloud's default is not a posture "
        "anyone chose; say it explicitly.")


def test_the_connector_deploy_grants_someone_before_it_closes_the_door():
    """Closing a service without granting an invoker is an outage, not a fix.
    The deploy has to do both, or the first person to run it loses access to
    the connector and has no obvious way back."""
    text = DEPLOY.read_text()
    grant = re.search(
        r"add-iam-policy-binding dmai-mcp\b[\s\S]{0,400}?roles/run\.invoker",
        text)
    assert grant, ("infra/deploy.sh closes dmai-mcp but never grants "
                   "roles/run.invoker to anything — nobody could call it")


def test_the_deploy_verifies_the_posture_it_just_set():
    """A grant that was applied is not a service that rejects anonymous calls;
    IAM is eventually consistent and a typo in a member string fails quietly.
    The deploy probes it and refuses to report success on anything but a
    rejection — the same token-free probe the install doctor makes."""
    text = DEPLOY.read_text()
    assert "deploy-probe-no-such-path-token" in text, (
        "the deploy sets the posture but never measures it")
    probe = text[text.find("deploy-probe-no-such-path-token"):]
    assert re.search(r"401\|403|403\|401", probe), (
        "the probe does not treat 401/403 as the passing answer")
    assert "exit 1" in probe[:1200], (
        "the probe reports but does not FAIL the deploy; a warning in a "
        "release log is not a gate")


def test_web_is_exempt_and_the_reason_is_written_down():
    """`dmai-web` IS deployed public, correctly — IAP sits in front of it and
    does the authenticating. That exemption is load-bearing, so it must be
    explained in the file rather than inferred from its absence here."""
    text = DEPLOY.read_text()
    assert "dmai-web" in text and "iap" in text.lower(), (
        "dmai-web is deployed public with no IAP configuration in the same "
        "file; either it is protected somewhere unstated or it is exposed")
