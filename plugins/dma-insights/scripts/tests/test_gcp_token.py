"""gcp_token.py builds a JWT Google will accept — provable without Google.

The exchange endpoint is not called here (CI must pass offline); what IS
provable locally is everything Google validates before its signature check
succeeds: base64url encoding without padding, the exact header, the claim
set for each mode, and an RS256 signature that verifies against the public
half of the key that signed it. A throwaway RSA key is generated per test
run — no real credential exists anywhere in this file or its fixtures.
"""
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gcp_token  # noqa: E402


@pytest.fixture(scope="module")
def throwaway_key(tmp_path_factory):
    """A fresh 2048-bit RSA key pair, PEM, never persisted beyond the test."""
    d = tmp_path_factory.mktemp("keys")
    priv, pub = d / "k.pem", d / "k.pub"
    subprocess.run(["openssl", "genrsa", "-out", str(priv), "2048"],
                   capture_output=True, check=True)
    subprocess.run(["openssl", "rsa", "-in", str(priv), "-pubout",
                    "-out", str(pub)], capture_output=True, check=True)
    return {"private_pem": priv.read_text(), "public_path": pub}


def _decode_part(part: bytes) -> dict:
    pad = b"=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part + pad))


def test_b64url_strips_padding():
    # one, two and zero padding chars in standard base64
    for raw in (b"a", b"ab", b"abc", b"\xfb\xff\xfe"):
        out = gcp_token._b64url(raw)
        assert b"=" not in out
        assert b"+" not in out and b"/" not in out


def test_unsigned_jwt_header_is_rs256():
    unsigned = gcp_token.build_unsigned_jwt({"iss": "x"})
    header, payload = unsigned.split(b".")
    assert _decode_part(header) == {"alg": "RS256", "typ": "JWT"}
    assert _decode_part(payload) == {"iss": "x"}


def test_id_mode_claims_carry_target_audience(throwaway_key):
    key = {"client_email": "t@example.iam.gserviceaccount.com",
           "private_key": throwaway_key["private_pem"]}
    before = int(time.time())
    jwt = gcp_token.mint_assertion(key, {"target_audience": "https://aud"})
    _, payload, _ = jwt.encode().split(b".")
    claims = _decode_part(payload)
    assert claims["iss"] == claims["sub"] == key["client_email"]
    assert claims["aud"] == gcp_token.TOKEN_URL
    assert claims["target_audience"] == "https://aud"
    assert before <= claims["iat"] <= claims["exp"] == claims["iat"] + 3600


def test_access_mode_claims_carry_scope(throwaway_key):
    key = {"client_email": "t@example.iam.gserviceaccount.com",
           "private_key": throwaway_key["private_pem"]}
    jwt = gcp_token.mint_assertion(key, {"scope": gcp_token.DEFAULT_SCOPE})
    claims = _decode_part(jwt.encode().split(b".")[1])
    assert claims["scope"] == gcp_token.DEFAULT_SCOPE
    assert "target_audience" not in claims


def test_signature_verifies_against_public_key(throwaway_key, tmp_path):
    key = {"client_email": "t@example.iam.gserviceaccount.com",
           "private_key": throwaway_key["private_pem"]}
    jwt = gcp_token.mint_assertion(key, {"target_audience": "https://aud"})
    head, payload, sig = jwt.encode().split(b".")
    signing_input = head + b"." + payload
    sig_raw = base64.urlsafe_b64decode(sig + b"=" * (-len(sig) % 4))
    sig_file = tmp_path / "sig.bin"
    sig_file.write_bytes(sig_raw)
    proc = subprocess.run(
        ["openssl", "dgst", "-sha256", "-verify",
         str(throwaway_key["public_path"]), "-signature", str(sig_file)],
        input=signing_input, capture_output=True)
    assert proc.returncode == 0, proc.stderr


def test_signature_does_not_verify_when_tampered(throwaway_key, tmp_path):
    """Negative control: the verify step must be able to fail."""
    key = {"client_email": "t@example.iam.gserviceaccount.com",
           "private_key": throwaway_key["private_pem"]}
    jwt = gcp_token.mint_assertion(key, {"target_audience": "https://aud"})
    head, payload, sig = jwt.encode().split(b".")
    tampered = head + b"." + payload + b"x"
    sig_raw = base64.urlsafe_b64decode(sig + b"=" * (-len(sig) % 4))
    sig_file = tmp_path / "sig.bin"
    sig_file.write_bytes(sig_raw)
    proc = subprocess.run(
        ["openssl", "dgst", "-sha256", "-verify",
         str(throwaway_key["public_path"]), "-signature", str(sig_file)],
        input=tampered, capture_output=True)
    assert proc.returncode != 0


def test_missing_key_file_exits_2(monkeypatch, capsys, tmp_path):
    """No file AND no key in the environment is the only real 'no key' case —
    load_key reaches the environment before giving up, so the fixture has to
    clear it to test the failure path."""
    for var in ("DMA_ROUTINE_SA_KEY_B64", "DMA_ROUTINE_SA_KEY"):
        monkeypatch.delenv(var, raising=False)
    rc = gcp_token.main(["id", "--audience", "https://aud",
                         "--key", str(tmp_path / "absent" / "sa.json")])
    assert rc == 2
    captured = capsys.readouterr()
    assert captured.out == ""          # nothing but tokens ever on stdout
    assert "no usable key" in captured.err
