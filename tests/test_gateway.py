"""Gateway: config materialization, TLS resolution, operator surface."""

import importlib.util

import pytest

from easyremote.errors import InvalidArgument, Unavailable
from easyremote.gateway import Gateway, TLSConfig

HAS_CRYPTOGRAPHY = importlib.util.find_spec("cryptography") is not None

# A minimal self-signed cert (PEM) is only obtainable via cryptography;
# tests that need real PEM bytes are gated on the optional extra.
needs_cryptography = pytest.mark.skipif(
    not HAS_CRYPTOGRAPHY, reason="optional [gateway] extra not installed"
)


class FakeDaemon:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def make_gateway(tmp_path, tls, **kwargs):
    started = []

    def starter(config):
        started.append(config)
        return FakeDaemon()

    gateway = Gateway(
        8443, realm="acme", tls=tls, home=tmp_path, daemon_starter=starter, **kwargs
    )
    return gateway, started


def write_fake_pem(tmp_path):
    # Structurally valid PEM (base64 payload) — enough for fingerprint
    # math, which never parses X.509.
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text(
        "-----BEGIN CERTIFICATE-----\nAAECAwQFBgc=\n-----END CERTIFICATE-----\n"
    )
    key.write_text("-----BEGIN PRIVATE KEY-----\nAAA=\n-----END PRIVATE KEY-----\n")
    return TLSConfig(cert_pem=cert, key_pem=key)


def test_start_writes_pinned_hub_config_and_passes_ffi_shape(tmp_path):
    tls = write_fake_pem(tmp_path)
    gateway, started = make_gateway(tmp_path, tls)
    gateway.start()

    assert started == [{"mode": "hub", "realm": "acme"}]  # ffi/daemon.rs:52 shape

    config = (tmp_path / "daemon-config.toml").read_text()
    assert 'mode = "hub"' in config
    assert 'realm = "acme"' in config
    assert 'listen_tcp = "0.0.0.0:8443"' in config
    assert f'tls_cert_pem = "{tls.cert_pem}"' in config
    assert f'tls_key_pem = "{tls.key_pem}"' in config


def test_existing_config_is_never_rewritten(tmp_path):
    existing = tmp_path / "daemon-config.toml"
    existing.write_text('# operator-authored\n[daemon]\nmode = "hub"\n')
    gateway, _ = make_gateway(tmp_path, write_fake_pem(tmp_path))
    gateway.start()
    assert existing.read_text().startswith("# operator-authored")


def test_stop_stops_daemon(tmp_path):
    gateway, _ = make_gateway(tmp_path, write_fake_pem(tmp_path))
    gateway.start()
    daemon = gateway._daemon
    gateway.stop()
    assert daemon.stopped


def test_fingerprint_is_sha256_of_der(tmp_path):
    import hashlib

    tls = write_fake_pem(tmp_path)
    gateway, _ = make_gateway(tmp_path, tls)
    expected = hashlib.sha256(bytes(range(8))).hexdigest().upper()
    assert gateway.fingerprint.replace(":", "") == expected


def test_pairing_guidance_mentions_endpoint_and_fingerprint(tmp_path):
    gateway, _ = make_gateway(tmp_path, write_fake_pem(tmp_path))
    guidance = gateway.pairing_guidance
    assert "easynet pair" in guidance
    assert ":8443" in guidance
    assert gateway.fingerprint in guidance


def test_missing_tls_files_rejected(tmp_path):
    with pytest.raises(InvalidArgument, match="not found"):
        Gateway(
            tls=TLSConfig(tmp_path / "no.pem", tmp_path / "no.key"), home=tmp_path
        ).start()


def test_acme_is_an_honest_open_question(tmp_path):
    with pytest.raises(Unavailable) as exc_info:
        Gateway(tls="acme", home=tmp_path)
    assert exc_info.value.reason == "acme_pending"


def test_self_signed_without_cryptography_is_actionable(tmp_path, monkeypatch):
    if HAS_CRYPTOGRAPHY:
        pytest.skip("cryptography installed; the error path is unreachable")
    gateway, _ = make_gateway(tmp_path, "self-signed")
    with pytest.raises(Unavailable) as exc_info:
        gateway.start()
    assert exc_info.value.reason == "cryptography_not_installed"
    assert "easyremote[gateway]" in str(exc_info.value)


@needs_cryptography
def test_self_signed_provisioning_round_trip(tmp_path):
    gateway, started = make_gateway(tmp_path, "self-signed")
    gateway.start()
    cert = tmp_path / "gateway" / "self-signed.cert.pem"
    key = tmp_path / "gateway" / "self-signed.key.pem"
    assert cert.exists() and key.exists()
    assert (key.stat().st_mode & 0o777) == 0o600
    assert len(gateway.fingerprint.split(":")) == 32
    assert started  # daemon started after provisioning
