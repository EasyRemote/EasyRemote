"""Server: run this machine as the realm hub (SPEC §5.3).

The classic EasyRemote name is kept: the Server has always been the
rendezvous everyone connects to — in EasyNet terms, the hub.

Verified contracts (EasyNet-Cli sources):

- start config: ``easynet_daemon_start({"mode": "hub", "realm": ...})``
  (``ffi/daemon.rs:48`` — no TLS fields ride the FFI call);
- hub boot reads ``~/.easynet/daemon-config.toml``:
  ``[daemon] mode/realm/listen_tcp/tls_cert_pem/tls_key_pem``
  (``daemon_config.rs::ensure_hub_config``), with **create-only-if-
  absent** semantics — an operator-authored config always wins;
- Invariant 2: a TCP listener without both TLS paths refuses to boot.
  Accordingly this module has **no plaintext option**.

Self-signed provisioning needs the optional ``cryptography``
dependency (``pip install easyremote[gateway]``); operators with real
certificates pass :class:`TLSConfig` and need nothing extra.
"""

from __future__ import annotations

import base64
import hashlib
import json
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from .config import settings
from .daemon import DaemonHandle, DaemonStartConfig
from .errors import InvalidArgument, Unavailable

__all__ = ["Gateway", "Server", "TLSConfig"]

@dataclass(frozen=True)
class TLSConfig:
    """Operator-provided TLS material for the hub listener."""

    cert_pem: Path
    key_pem: Path

    def validate(self) -> TLSConfig:
        for path in (self.cert_pem, self.key_pem):
            if not Path(path).exists():
                raise InvalidArgument(
                    f"TLS file not found: {path}", reason="tls_file_missing"
                )
        return self


class Server:
    """The realm hub, wrapped: provision TLS, write minimal config, start.

    ``daemon_starter``/``home`` are injectable seams (tests); production
    code never passes them.
    """

    def __init__(
        self,
        port: int = 8443,
        *,
        realm: str = "localhost",
        tls: TLSConfig | Literal["self-signed", "acme"] = "self-signed",
        home: Path | None = None,
        daemon_starter: Callable[[DaemonStartConfig], DaemonHandle] | None = None,
    ) -> None:
        # DaemonMode::Both exists daemon-side, but the FFI start config
        # only accepts "device" | "hub" (ffi/daemon.rs:52) — so this
        # facade only offers hub. Backend co-location boots its daemon
        # through the CLI, not through here.
        if tls == "acme":
            raise Unavailable(
                "ACME provisioning is an open SPEC question (§12.2) — use"
                " self-signed + fingerprint pinning, or bring certificates"
                " via TLSConfig",
                reason="acme_pending",
            )
        if not isinstance(tls, TLSConfig) and tls != "self-signed":
            raise InvalidArgument(
                f"tls must be 'self-signed' or a TLSConfig, got {tls!r}",
                reason="invalid_tls_choice",
            )
        self._port = port
        self._realm = realm.strip() or "localhost"
        self._tls = tls
        # Keep gateway material beside the SDK-owned daemon discovery root;
        # callers that configure a custom EasyNet control path automatically
        # get the same process-wide state root here.
        self._home = home or settings().control_path.parent
        self._daemon_starter = daemon_starter or DaemonHandle.start
        self._daemon: DaemonHandle | None = None
        self._gateway = _GatewayLifecycle(
            lambda realm: self._daemon_starter(DaemonStartConfig.hub(realm))
        )
        self._runtime: _GatewayRuntime | None = None
        self._tls_config: TLSConfig | None = None
        self._stop_event = threading.Event()

    # -- lifecycle ----------------------------------------------------------

    def start(self, block: bool = False) -> None:
        self._start_once()
        if block:
            try:
                self._stop_event.wait()
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()

    def stop(self) -> None:
        try:
            self._gateway.stop()
        finally:
            self._runtime = None
            self._daemon = None
            self._stop_event.set()

    def __enter__(self) -> Server:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    # -- operator surface --------------------------------------------------------

    @property
    def endpoint(self) -> str:
        runtime = self._runtime
        if runtime is not None:
            return runtime.endpoint
        return f"{socket.gethostname()}:{self._port}"

    @property
    def fingerprint(self) -> str:
        """SHA-256 of the listener certificate (DER), colon-hex.

        Nodes pin this out-of-band when the certificate is self-signed.
        """
        runtime = self._runtime
        if runtime is not None:
            return runtime.fingerprint
        tls = self._tls_config or self._resolve_tls()
        return _certificate_fingerprint(tls.cert_pem)

    @property
    def pairing_guidance(self) -> str:
        """Human instructions for joining a node to this hub.

        Deliberately *instructions*, not a fabricated command line: the
        exact ``easynet pair`` flag surface belongs to EasyNet-Cli and
        is pinned in P0. What a node operator needs is here: endpoint
        and fingerprint.
        """
        return (
            f"On each node, run `easynet pair` against {self.endpoint}"
            f" (realm {self._realm}). TLS fingerprint to verify:"
            f" {self.fingerprint}"
        )

    # -- internals --------------------------------------------------------------

    def _resolve_tls(self) -> TLSConfig:
        if isinstance(self._tls, TLSConfig):
            return self._tls
        cert = self._home / "gateway" / "self-signed.cert.pem"
        key = self._home / "gateway" / "self-signed.key.pem"
        if not (cert.exists() and key.exists()):
            _generate_self_signed(cert, key)
        return TLSConfig(cert_pem=cert, key_pem=key)

    def _start_once(self) -> None:
        self._stop_event.clear()
        tls = self._resolve_tls()
        runtime = self._gateway.start(
            _GatewayConfig(
                port=self._port,
                realm=self._realm,
                home_dir=self._home,
                tls_cert_path=tls.cert_pem,
                tls_key_path=tls.key_pem,
                hostname=socket.gethostname(),
            )
        )
        self._tls_config = tls
        self._runtime = runtime
        self._daemon = runtime.daemon


def _generate_self_signed(cert_path: Path, key_path: Path) -> None:
    """Provision a self-signed ECDSA P-256 certificate (10-year validity).

    Trust comes from fingerprint pinning at pairing time, not from the
    certificate chain — hence self-signed is sound here.
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
    except ImportError:
        raise Unavailable(
            "self-signed TLS provisioning needs the optional dependency:"
            " pip install 'easyremote[gateway]' — or bring certificates"
            " via TLSConfig",
            reason="cryptography_not_installed",
        ) from None

    import datetime

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "easyremote-gateway")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.DNSName(socket.gethostname()),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))


# SPEC §5.3 alias — same object, the architectural term.
Gateway = Server


class _GatewayState(Enum):
    IDLE = "idle"
    RUNNING = "running"


@dataclass(frozen=True)
class _GatewayConfig:
    port: int
    realm: str
    home_dir: Path
    tls_cert_path: Path
    tls_key_path: Path
    hostname: str

    def validate(self) -> _GatewayConfig:
        if not 1 <= self.port <= 65535:
            raise InvalidArgument(
                "gateway port must be between 1 and 65535",
                reason="invalid_gateway_port",
            )
        TLSConfig(self.tls_cert_path, self.tls_key_path).validate()
        return self

    @property
    def config_path(self) -> Path:
        return self.home_dir / "daemon-config.toml"

    @property
    def endpoint(self) -> str:
        return f"{self.hostname or 'localhost'}:{self.port}"


@dataclass(frozen=True)
class _GatewayRuntime:
    endpoint: str
    fingerprint: str
    config_path: Path
    daemon: DaemonHandle


class _GatewayLifecycle:
    """Product-owned hub provisioning around the generic daemon lifecycle."""

    def __init__(self, daemon_starter: Callable[[str], DaemonHandle]) -> None:
        self._daemon_starter = daemon_starter
        self._state = _GatewayState.IDLE
        self._runtime: _GatewayRuntime | None = None
        self._lock = threading.Lock()

    def start(self, config: _GatewayConfig) -> _GatewayRuntime:
        normalized = config.validate()
        with self._lock:
            if self._state is _GatewayState.RUNNING:
                assert self._runtime is not None
                return self._runtime
            _ensure_hub_config(normalized)
            daemon = self._daemon_starter(normalized.realm.strip() or "localhost")
            runtime = _GatewayRuntime(
                endpoint=normalized.endpoint,
                fingerprint=_certificate_fingerprint(normalized.tls_cert_path),
                config_path=normalized.config_path,
                daemon=daemon,
            )
            self._runtime = runtime
            self._state = _GatewayState.RUNNING
            return runtime

    def stop(self) -> None:
        with self._lock:
            runtime = self._runtime
            self._runtime = None
            self._state = _GatewayState.IDLE
        if runtime is not None:
            runtime.daemon.stop()


def _ensure_hub_config(config: _GatewayConfig) -> None:
    path = config.config_path
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Auto-generated by EasyRemote. Operator-authored files are preserved.\n"
        "[daemon]\n"
        'mode = "hub"\n'
        f"realm = {json.dumps(config.realm.strip() or 'localhost')}\n"
        f"listen_tcp = {json.dumps(f'0.0.0.0:{config.port}')}\n"
        f"tls_cert_pem = {json.dumps(str(config.tls_cert_path))}\n"
        f"tls_key_pem = {json.dumps(str(config.tls_key_path))}\n",
        encoding="utf-8",
    )


def _certificate_fingerprint(cert_path: Path) -> str:
    try:
        lines = [
            line
            for line in cert_path.read_text(encoding="ascii").splitlines()
            if line and not line.startswith("-----")
        ]
        der = base64.b64decode("".join(lines), validate=True)
    except Exception as exc:
        raise InvalidArgument(
            "TLS certificate must be PEM encoded",
            reason="invalid_tls_certificate",
        ) from exc
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[index : index + 2] for index in range(0, len(digest), 2))
