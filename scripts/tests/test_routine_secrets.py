

def test_the_fallback_path_reaches_the_identity_the_doc_is_shared_with(monkeypatch):
    import json
    """The measured production failure: gcloud impersonation is unavailable in
    the scheduled session, so the loader falls back to the stored key — and
    read Drive as the KEY's own account, which the secrets doc was never
    shared with. The doc 404'd and the run reported "not retrieving the keys"
    while the doc was correctly shared with dmai-worker all along.

    The fallback now spends the key on an impersonated token for the same
    account the primary path uses, so both paths read as one identity.
    """
    import routine_secrets as R

    calls = {"cloud_platform_scope": None, "impersonation_target": None}

    def fake_key_token(scope):
        calls["cloud_platform_scope"] = scope
        return "key-token-" + "x" * 120

    def fake_impersonate(token, target, scope):
        calls["impersonation_target"] = target
        # iamcredentials refuses a Drive-scoped token; the caller must
        # authenticate this exchange at cloud-platform. If it ever passes the
        # Drive token again, this returns None and the test fails below.
        if token.startswith("key-token-"):
            return "impersonated-" + "y" * 120
        return None

    monkeypatch.setattr(R, "_key_token", fake_key_token)
    monkeypatch.setattr(R, "_impersonate_with", fake_impersonate)
    monkeypatch.setattr(R, "secret", lambda name, **k: json.dumps({
        "client_email": "stored-key@example.iam.gserviceaccount.com",
        "private_key_id": "kid", "private_key": "unused",
        "token_uri": "https://oauth2.googleapis.com/token"}))
    monkeypatch.setattr(R.subprocess, "run", lambda *a, **k: _Refused())
    R._cache.clear()

    tok, how = R.drive_token()

    assert calls["cloud_platform_scope"] == R._CLOUD_PLATFORM, (
        "the impersonation exchange must be authenticated at cloud-platform; "
        "a Drive-scoped token is refused by iamcredentials and the upgrade "
        "silently never happens")
    assert calls["impersonation_target"] == R.DRIVE_IMPERSONATE
    assert R.drive_identity() == R.DRIVE_IMPERSONATE, (
        "the fallback must end up as the account the doc and the intake tree "
        "are shared with, not as the stored key's own account")
    assert tok.startswith("impersonated-")
    assert "via the stored key" in how, "the path taken must stay visible"


class _Refused:
    returncode = 1
    stdout = b""
    stderr = b"simulated: gcloud impersonation unavailable"
