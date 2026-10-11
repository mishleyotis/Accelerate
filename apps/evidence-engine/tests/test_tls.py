"""The trust store: system roots + certifi + the environment's bundle, never off."""
import ssl

from evidence_engine import tls


def test_trust_context_is_a_verifying_context_and_reads_the_env_bundle(tmp_path, monkeypatch):
    tls.reset()
    ctx = tls.trust_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    before = ctx.cert_store_stats()["x509_ca"]
    # a bundle the environment names is ADDED, not substituted
    pem = tmp_path / "extra.pem"
    pem.write_bytes(ssl.DER_cert_to_PEM_cert(_self_signed_der()).encode())
    monkeypatch.setenv("SSL_CERT_FILE", str(pem))
    tls.reset()
    ctx2 = tls.trust_context()
    assert ctx2.cert_store_stats()["x509_ca"] >= before + 1
    tls.reset()


def test_a_missing_or_broken_bundle_path_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "nope.pem"))
    bad = tmp_path / "bad.pem"; bad.write_text("not a certificate")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(bad))
    tls.reset()
    assert tls.trust_context().verify_mode == ssl.CERT_REQUIRED
    tls.reset()


def _self_signed_der() -> bytes:
    """A throwaway CA certificate generated at test time (no key material committed)."""
    import datetime as dt
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "evidence-engine test CA")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.DER)
