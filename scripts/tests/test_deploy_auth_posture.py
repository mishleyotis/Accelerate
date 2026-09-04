"""Identity posture, asserted where it is decided — and its 2026-08-20 turn.

`infra/deploy.sh` passed `--allow-unauthenticated` for `dmai-mcp` until
2026-08-16. That flag grants roles/run.invoker to allUsers. The plugin minted
a Google identity token on every connection and sent it; nothing on the other
side read it, so authentication rested entirely on a 32-character path token
travelling in a URL — on the single component permitted to write serving
content. The 2026-08-16 fix closed ingress at IAM, and this file pinned it.

On 2026-08-20 the owner directed a different contract (docs/DECISIONS.md D8):
the connector must be installable from claude.ai's custom-connector dialog —
whose client speaks OAuth, not Google IAM — with any verified @zennify.com
account authorized. Ingress reopened, and the identity check moved INTO the
app (apps/mcp/dma_mcp/oauth_gate.py), which READS every request's bearer:
that is the difference between this and the pre-2026-08-16 state, and it is
exactly what these tests now assert. The defect class stays impossible: a
deploy line that opens ingress WITHOUT the in-app gate wired fails CI red.

`dmai-api` remains IAM-closed; `dmai-web` remains public behind IAP. This is
a text test on purpose: it needs no GCP credentials, so it runs on every
commit — where a silently reopened (or silently unguarded) service has to be
caught, not at deploy time when the argument for shipping anyway is
strongest.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "infra" / "deploy.sh"
GATE = ROOT / "apps" / "mcp" / "dma_mcp" / "oauth_gate.py"
SERVER = ROOT / "apps" / "mcp" / "server.py"

#: Services that must never be reachable without a Google identity at IAM.
#: `dmai-web` is deliberately absent (public behind IAP); `dmai-mcp` moved to
#: the gated set below on 2026-08-20 (D8).
CLOSED_SERVICES = {
    "dmai-api": "serves promoted client content, including internal audiences",
}

PUBLIC_FLAG = re.compile(r"(?<!-)(?<!no-)--allow-unauthenticated\b")


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
    assert not PUBLIC_FLAG.search(block), (
        f"{service} is deployed with --allow-unauthenticated, which grants "
        f"roles/run.invoker to allUsers. {CLOSED_SERVICES[service]}. "
        "Use --no-allow-unauthenticated and grant the specific principals "
        "that must invoke it.")
    assert "--no-allow-unauthenticated" in block, (
        f"{service} states neither --allow-unauthenticated nor "
        "--no-allow-unauthenticated. gcloud's default is not a posture "
        "anyone chose; say it explicitly.")


def test_THE_CONNECTOR_IS_PUBLIC_ONLY_WITH_THE_GATE_STANDING():
    """The D8 contract, both halves — and the 2026-08-16 defect class held
    impossible: open ingress may appear ONLY together with the in-app gate
    that reads every bearer. Remove or unwire the gate and this fails red
    before any deploy runs."""
    block = _deploy_block("dmai-mcp")
    assert PUBLIC_FLAG.search(block), (
        "dmai-mcp is no longer deployed --allow-unauthenticated; if the D8 "
        "contract has been reversed, restore this file's 2026-08-16 shape "
        "(CLOSED_SERVICES) deliberately rather than leaving both halves "
        "ambiguous")
    assert GATE.is_file(), (
        "dmai-mcp deploys PUBLIC but apps/mcp/dma_mcp/oauth_gate.py is gone "
        "— that is the pre-2026-08-16 defect verbatim: open ingress with "
        "nothing reading identity")
    gate_src = GATE.read_text()
    for needle, why in [
        ("class OAuthGate", "the ASGI gate class"),
        ("def check_identity", "the pure policy function"),
        ("zennify.com", "the authorized domain default"),
        ("tokeninfo", "rung B validation against Google"),
        ("WWW-Authenticate".lower(), "the 401 challenge header (lowercase "
                                     "wire form) claude.ai discovery needs"),
    ]:
        assert needle.lower() in gate_src.lower(), (
            f"oauth_gate.py no longer carries {why} ({needle!r})")
    server_src = SERVER.read_text()
    assert "OAuthGate" in server_src, (
        "server.py builds the app without wrapping OAuthGate — the gate "
        "exists but nothing routes requests through it")
    assert "MCP_SERVICE_URL" in block, (
        "the deploy no longer pins MCP_SERVICE_URL, the audience rung-A "
        "service tokens are checked against")


def test_the_connector_deploy_grants_someone_before_it_closes_the_door():
    """The invoker grants stay: inert under open ingress, load-bearing the
    moment ingress is ever re-closed — losing them silently would turn a
    future re-close into an outage."""
    text = DEPLOY.read_text()
    grant = re.search(
        r"add-iam-policy-binding dmai-mcp\b[\s\S]{0,400}?roles/run\.invoker",
        text)
    assert grant, ("infra/deploy.sh no longer grants roles/run.invoker on "
                   "dmai-mcp to anyone — a future ingress re-close would "
                   "lock everyone out")


def test_the_deploy_verifies_the_posture_it_just_set():
    """A gate that was written is not a service that refuses anonymous calls;
    the deploy probes the LIVE service and refuses to report success unless
    an anonymous /mcp call is refused in-app (401) AND the OAuth discovery
    document is public (200) — both halves of the D8 contract, measured."""
    text = DEPLOY.read_text()
    start = text.find("Prove it rather than assuming it")
    assert start != -1, "the deploy sets the posture but never measures it"
    probe = text[start:start + 1600]
    assert "/.well-known/oauth-protected-resource" in probe, (
        "the probe never checks that OAuth discovery is public")
    assert re.search(r'"\$code"\s*=\s*"401"', probe), (
        "the probe does not require the anonymous call to be refused 401 "
        "by the app")
    assert "exit 1" in probe, (
        "the probe reports but does not FAIL the deploy; a warning in a "
        "release log is not a gate")


def test_web_is_exempt_and_the_reason_is_written_down():
    """`dmai-web` is exempt from the closed-at-IAM rule because IAP sits in
    front of it and does the authenticating. That exemption is load-bearing,
    so it must be explained in the file rather than inferred from its
    absence here."""
    text = DEPLOY.read_text()
    assert "dmai-web" in text and "iap" in text.lower(), (
        "dmai-web is deployed public with no IAP configuration in the same "
        "file; either it is protected somewhere unstated or it is exposed")


def _web_deploy_block() -> str:
    """The `gcloud run deploy dmai-web` invocation, flags and all."""
    text = DEPLOY.read_text()
    i = text.index("gcloud run deploy dmai-web")
    # up to the first line that is not a continuation of the command
    out = []
    for line in text[i:].splitlines():
        out.append(line)
        if not line.rstrip().endswith("\\"):
            break
    return "\n".join(out)


def test_the_web_deploy_does_not_re_open_the_door_it_then_closes():
    """MEASURED 2026-09-04, in a release log.

    The IAP block was rewritten on 2026-09-01 to converge — "read first and
    write only when the state is actually wrong" — after a user loading the
    app at 17:56:03 got IAP `Error code: 11` while that block rebuilt the
    door around them. It still wrote on every release, because this command
    two blocks earlier passed `--allow-unauthenticated` and re-granted
    `allUsers`; the converge step then dutifully found it and removed it.
    A guaranteed SetIamPolicy on the door, every release, from a block whose
    entire purpose was to stop doing that.

    On an existing service gcloud touches the IAM policy only when one of
    the two flags is given. So the web deploy must give NEITHER, and the
    converge block owns dmai-web's policy alone."""
    block = _web_deploy_block()
    assert PUBLIC_FLAG.search(block) is None, (
        "the dmai-web deploy passes --allow-unauthenticated, which re-grants "
        "allUsers on every release and forces the IAP converge block to "
        "write to the service IAM policy every time — the churn that "
        "produced IAP Error code: 11")
    assert "--no-allow-unauthenticated" not in block, (
        "the dmai-web deploy passes --no-allow-unauthenticated; that is also "
        "an IAM write on a door IAP's converge block already owns. Pass "
        "neither flag and let that block read-then-write")


def test_the_converge_block_still_owns_the_web_door():
    """Dropping the flag is only safe because something else guarantees the
    two bindings that matter. If this block stops granting the IAP service
    agent, dmai-web becomes uninvokable by the only principal that reaches
    it."""
    text = DEPLOY.read_text()
    i = text.index("IAP_SA=")
    block = text[i:i + 2500]
    assert "add-iam-policy-binding dmai-web" in block and "IAP_SA" in block, (
        "nothing grants the IAP service agent run.invoker on dmai-web; with "
        "no --allow-unauthenticated on the deploy either, the door has no "
        "one behind it")
    assert "allUsers" in block and "remove-iam-policy-binding" in block, (
        "nothing removes a public invoker grant from dmai-web, so one added "
        "by hand would never be converged away")


# ── the OAuth secrets a deploy must carry, derived from the code ──────────
#
# `--set-secrets` REPLACES the container's whole secret set; it does not merge
# with the previous revision's. So a secret bound by hand onto one revision is
# dropped by the very next deploy, silently, and stays dropped until someone
# tries to sign in.
#
# That happened. `deploy.sh` scripted OAUTH_CLIENT_ID; OAUTH_CLIENT_SECRET and
# OAUTH_SIGNING_KEY were created later and bound by hand onto revision 00101.
# Deploy 16 rolled 00102 from the script and /authorize started answering
# "authorization server not configured: OAUTH_CLIENT_ID and OAUTH_SIGNING_KEY
# must be wired from Secret Manager" — a connector verified end-to-end 39/39
# broken by a deploy that changed no code. The end-to-end verifier caught it
# only because it was re-run; nothing failed at deploy time.
#
# The list is READ FROM `oauth_as.py`, never restated, so a newly required
# variable fails this test on the commit that introduces it rather than on the
# deploy that drops it.

OAUTH_AS = ROOT / "apps" / "mcp" / "dma_mcp" / "oauth_as.py"


def _oauth_env_vars_the_code_requires() -> set:
    import ast
    tree = ast.parse(OAUTH_AS.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        # os.environ.get("OAUTH_…")
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value.startswith("OAUTH_")):
            names.add(node.args[0].value)
    return names


def test_the_authorization_server_reads_the_three_we_think_it_does():
    """A guard on the guard: if this set changes, the wiring test below is
    checking the wrong thing and should be read again, not silently widened."""
    assert _oauth_env_vars_the_code_requires() == {
        "OAUTH_CLIENT_ID", "OAUTH_CLIENT_SECRET", "OAUTH_SIGNING_KEY"}


def test_every_oauth_variable_the_code_reads_is_wired_by_the_deploy():
    src = DEPLOY.read_text(encoding="utf-8")
    for var in sorted(_oauth_env_vars_the_code_requires()):
        secret = var.lower().replace("_", "-").replace("oauth-", "dmai-oauth-")
        assert secret in src, (
            f"{var} is read by oauth_as.py and Secret Manager holds {secret}, "
            f"but infra/deploy.sh never wires it — --set-secrets replaces the "
            f"whole set, so the next deploy drops it and sign-in breaks with "
            f"no code change")
        assert f"{var}=" in src, (
            f"{secret} is named in deploy.sh but not bound to {var}")


def test_the_mcp_secret_set_is_built_in_one_place():
    """One variable carries every secret into --set-secrets. Two builders
    would let one of them be complete and the other not — which is the shape
    of the bug this file is about, one level up."""
    src = DEPLOY.read_text(encoding="utf-8")
    assert src.count('--set-secrets="$MCP_SECRETS"') == 1
    assert 'MCP_SECRETS="MCP_PATH_TOKEN=dmai-mcp-path-token:latest"' in src


def test_a_missing_oauth_secret_does_not_fail_the_release():
    """A project that has not created them yet still deploys — the gate then
    answers 401 naming what is missing. A deploy that hard-failed here would
    make the first deploy of a new environment impossible."""
    src = DEPLOY.read_text(encoding="utf-8")
    assert "gcloud secrets describe" in src
    assert "MCP_OAUTH_MISSING" in src
