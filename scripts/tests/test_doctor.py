"""The install doctor's two checks that decide whether it is worth running.

The AUDIENCE check is the one that can cry wolf; the ENFORCEMENT check is the
one whose absence let a public connector pass as healthy for weeks. Both
halves are below.

────────────────────────────────────────────────────────────────────────────
The audience check.

Cloud Run gives ONE service two hostnames. The plugin's default audience is
written in one form and `gcloud run services describe` prints the other, so
the check compares SERVICES, not hostnames — and a check that got that wrong
would fail on the default install, tell every operator their credentials were
misconfigured, and send them to fix something that was never broken.

Measured 2026-08-16 against production: all four combinations of {token
audienced at form A, at form B} x {called at form A, at form B} returned
HTTP 200. These tests hold the check to that measurement.

The other half is the one that matters more: a genuinely DIFFERENT service
must still fail. A check that passed everything would be worse than no check,
because it would be believed.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "dma_doctor", ROOT / "plugins" / "dma-insights" / "scripts" / "doctor.py")
doc = importlib.util.module_from_spec(_spec)
sys.modules["dma_doctor"] = doc
_spec.loader.exec_module(doc)

HASH_FORM = "https://dmai-mcp-dukrne5v4a-uc.a.run.app"
PROJNUM_FORM = "https://dmai-mcp-411520643589.us-central1.run.app"


def test_both_cloud_run_url_forms_name_the_same_service():
    assert doc._cloud_run_service("dmai-mcp-dukrne5v4a-uc.a.run.app") == "dmai-mcp"
    assert doc._cloud_run_service(
        "dmai-mcp-411520643589.us-central1.run.app") == "dmai-mcp"


def test_THE_DEFAULT_INSTALL_PASSES_ACROSS_URL_FORMS():
    """The regression this check exists to not be.

    `plugin.json` defaults the audience to the hash form; the install command
    in the README fills `mcp_base_url` from `gcloud run services describe`,
    which prints the project-number form. Comparing hostnames would fail here,
    on a correct install, every time.
    """
    for aud, url in ((HASH_FORM, PROJNUM_FORM), (PROJNUM_FORM, HASH_FORM)):
        result = doc.audience_check(aud, url)
        assert result["ok"], f"{aud} -> {url} reported a mismatch"
        assert "two Cloud Run URL forms" in result["detail"]


def test_the_same_url_needs_no_note_about_url_forms():
    result = doc.audience_check(HASH_FORM, HASH_FORM)
    assert result["ok"] and "two Cloud Run URL forms" not in result["detail"]


def test_A_DIFFERENT_SERVICE_STILL_FAILS():
    """The check has to keep its teeth. Pointing the plugin at a staging
    connector while the audience still names production is exactly the 403
    that reads like a permissions problem, and it must be named."""
    result = doc.audience_check(HASH_FORM,
                                "https://dmai-mcp-staging-abcdefghij-uc.a.run.app")
    assert not result["ok"]
    assert "dmai-mcp" in result["detail"] and "dmai-mcp-staging" in result["detail"]
    assert "DMA_MCP_HOST" in result["fix"]


def test_a_different_service_in_the_other_url_form_also_fails():
    result = doc.audience_check(
        HASH_FORM, "https://dmai-api-411520643589.us-central1.run.app")
    assert not result["ok"]


def test_an_unrecognised_hostname_falls_back_to_host_equality():
    """A custom domain or a localhost deployment parses as neither form. The
    fallback is host equality, NOT a pass: an unrecognised shape is not
    evidence that the audience is right, and passing by default is how a
    check becomes decoration."""
    assert doc._cloud_run_service("mcp.example.internal") is None
    assert doc.audience_check("https://mcp.example.internal",
                              "https://mcp.example.internal")["ok"]
    assert not doc.audience_check("https://mcp.example.internal",
                                  "https://other.example.internal")["ok"]


def test_no_base_url_says_it_compared_nothing():
    """Reporting `ok` for a comparison that did not happen is the
    CHECK_NEVER_RAN_READS_AS_UNKNOWN shape. It passes — there is nothing to
    fail against — but the detail has to say so, or an operator reads a green
    line as proof the audience was verified."""
    result = doc.audience_check(HASH_FORM, None)
    assert result["ok"]
    assert "nothing to compare" in result["detail"]
    assert "--base-url" in result["fix"]


def test_the_doctor_never_puts_a_token_in_its_output():
    """Every check reports whether a credential could be obtained, never what
    it was. Enforced on the source rather than on a run, because a run that
    happens not to mint a token proves nothing about one that does."""
    src = (ROOT / "plugins" / "dma-insights" / "scripts" / "doctor.py").read_text()
    # the mint check must report a fixed string, not the subprocess stdout
    assert '"yes (value not shown)"' in src
    assert "proc.stdout" not in src.split("identity token mints")[1].split(
        "connector path token")[0]


# ── the enforcement probe ──────────────────────────────────────────────────
#
# Until 2026-08-16 `dmai-mcp` granted roles/run.invoker to allUsers. Every
# check the doctor made passed — a token minted, its audience matched — while
# an anonymous POST reached the application. The checks measured that a
# credential EXISTED; none measured that anything ENFORCED it. These tests
# hold the new check to the distinction.


def test_iam_rejection_is_the_healthy_answer():
    for status in (401, 403):
        assert doc.classify_enforcement(status)["ok"], status


def test_A_PUBLIC_SERVICE_IS_THE_FINDING_NOT_A_PASS():
    """404 means the anonymous request was ROUTED — it got past IAM and only
    the application turned it away. That is a public service, and the whole
    point of this check is that it must not read as healthy."""
    result = doc.classify_enforcement(404)
    assert not result["ok"]
    assert "ANONYMOUS request reached the application" in result["detail"]
    assert "remove-iam-policy-binding" in result["fix"]
    assert "allUsers" in result["fix"]


def test_an_unreachable_connector_is_not_evidence_of_protection():
    """The CHECK_NEVER_RAN_READS_AS_UNKNOWN trap in its purest form: a probe
    that could not connect proves nothing, and must not bank a pass."""
    result = doc.classify_enforcement(None, "Name or service not known")
    assert not result["ok"]
    assert "not evidence that it is protected" in result["fix"]


def test_an_unexpected_status_does_not_get_the_benefit_of_the_doubt():
    for status in (200, 302, 500):
        result = doc.classify_enforcement(status)
        assert not result["ok"], status
    assert "unclear" in doc.classify_enforcement(200)["detail"]


def test_the_probe_carries_no_credential():
    """It is safe to ship precisely because it needs no secret: a bogus path
    token and no Authorization header. A probe that required the real token
    could not run before the token was configured — which is exactly when an
    operator most needs to know whether the deployment is open."""
    import inspect
    src = inspect.getsource(doc.enforcement_check)
    assert "probe-no-such-path-token" in src
    assert "Authorization" not in src
    assert "print-identity-token" not in src


def test_no_base_url_says_it_did_not_probe():
    result = doc.enforcement_check(None)
    assert result["ok"] and "not probed" in result["detail"]
