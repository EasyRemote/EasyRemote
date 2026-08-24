"""Target-device materialization for deployable EasyRemote ability bundles.

The caller's filesystem namespace is never projected onto the daemon. A bundle
is archived locally, uploaded through the target locomotion SystemAgent's
canonical ``fs.transfer`` bidi ability, and accepted only after its verified
terminal receipt proves byte count, digest, and cleanup completion.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import tarfile
import time
import uuid
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

import easynet_sdk

from ._sdk_transport import Transport
from .errors import InvalidArgument, RemoteError, Unavailable, error_from_sdk
from .invocation_policy import runtime_root_context

_CHUNK_BYTES = 64 * 1024
_RESOURCE_REF_TTL_MS = 5 * 60 * 1000


def stage_ability_bundle(
    transport: Transport,
    package: Path,
    *,
    caller_ura: str,
    locomotion_callee_ura: str,
    target_ura: str,
    timeout: float,
) -> dict[str, object]:
    """Upload one manifest bundle into the selected Device's tmp resource plane."""
    archive = _ability_bundle_archive(package)
    reference = _target_tmp_resource_ref(target_ura)
    session: easynet_sdk.BidiSession | None = None
    try:
        session = transport.open_runtime_ability_bidi(
            runtime_root_context(
                caller_ura=caller_ura,
                callee_ura=locomotion_callee_ura,
                subject_ura=str(reference["resource_ura"]),
            ),
            "fs.transfer",
            {"mode": "upload", "resource_ref": reference},
            (
                easynet_sdk.BidiStreamDescriptor(
                    stream_id=1,
                    content_type="application/json",
                    ordering="STRICT",
                ),
            ),
        )
        _send_archive(session, archive)
        _receive_completed_upload(
            session,
            timeout=timeout,
            expected_bytes=len(archive),
            expected_sha256=hashlib.sha256(archive).hexdigest(),
        )
        session.close()
        session = None
    except easynet_sdk.SDKError as exc:
        raise error_from_sdk(exc) from exc
    except RemoteError:
        raise
    except Exception as exc:
        raise Unavailable(
            f"ability bundle staging failed: {exc}",
            reason="ability_bundle_staging_failed",
        ) from exc
    finally:
        if session is not None:
            # Preserve the primary staging failure; close is best-effort on a
            # session whose canonical outcome is already non-successful.
            with suppress(easynet_sdk.SDKError):
                session.close()
    return reference


def _send_archive(session: easynet_sdk.BidiSession, archive: bytes) -> None:
    sequence = 1
    for offset in range(0, len(archive), _CHUNK_BYTES):
        chunk = archive[offset : offset + _CHUNK_BYTES]
        session.send(
            easynet_sdk.BidiFrame(
                sequence=sequence,
                kind="binary_chunk",
                stream_id=1,
                payload_content_type="application/octet-stream",
                payload_base64=base64.b64encode(chunk).decode("ascii"),
            )
        )
        sequence += 1
    session.send(
        easynet_sdk.BidiFrame(
            sequence=sequence,
            kind="eof",
            stream_id=1,
        )
    )


def _ability_bundle_archive(package: Path) -> bytes:
    manifest_path = package / "ability.json"
    if not manifest_path.is_file():
        raise InvalidArgument(
            f"ability package has no ability.json: {package}",
            reason="ability_manifest_missing",
        )
    manifest = manifest_path.read_bytes()
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        info = tarfile.TarInfo("ability.json")
        info.size = len(manifest)
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(manifest))
    return output.getvalue()


def _target_tmp_resource_ref(target_ura: str) -> dict[str, object]:
    try:
        target = easynet_sdk.parse_ura(target_ura)
    except easynet_sdk.SDKError as exc:
        raise InvalidArgument(
            f"invalid target_ura: {exc}",
            reason="invalid_target_ura",
        ) from exc
    if target.kind != "device":
        raise InvalidArgument(
            f"target_ura must name a Device, got {target.kind!r}",
            reason="invalid_target_ura",
        )
    relative = f"easynet-ability-deploy/{uuid.uuid4().hex}.tar.gz"
    try:
        resource = easynet_sdk.resource_ura(target_ura, f"fs/tmp/{relative}")
    except easynet_sdk.SDKError as exc:
        raise InvalidArgument(
            f"cannot build target staging ResourceRef: {exc}",
            reason="invalid_resource_path",
        ) from exc
    return {
        "resource_ura": resource,
        "owner_ura": target_ura,
        "namespace": "fs",
        "capability": "write",
        "expires_unix_ms": int(time.time() * 1000) + _RESOURCE_REF_TTL_MS,
        "revision": "fs-local-mapping-v1",
        "display_path": f"tmp/{relative}",
    }


def _receive_completed_upload(
    session: easynet_sdk.BidiSession,
    *,
    timeout: float,
    expected_bytes: int,
    expected_sha256: str,
) -> None:
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Unavailable(
                "fs.transfer did not complete before the client wait deadline",
                reason="ability_bundle_upload_timeout",
            )
        frame = session.receive(timeout=remaining)
        if frame.error is not None:
            raise Unavailable(
                f"fs.transfer failed while staging the ability bundle: {frame.error}",
                reason="ability_bundle_upload_failed",
            )
        payload = _upload_completion_payload(frame)
        if isinstance(payload, Mapping) and payload.get("type") in {
            "complete",
            "error",
        }:
            _require_completed_upload(
                payload,
                expected_bytes=expected_bytes,
                expected_sha256=expected_sha256,
            )
            return
        if frame.terminal or frame.transport_terminal:
            raise Unavailable(
                "fs.transfer reached terminal state without a completion payload",
                reason="invalid_upload_terminal",
            )


def _upload_completion_payload(
    frame: easynet_sdk.BidiFrame,
) -> Mapping[str, object] | None:
    if isinstance(frame.payload_json, Mapping):
        return frame.payload_json
    receipt = frame.terminal_receipt
    if not isinstance(receipt, Mapping):
        return None
    if (
        receipt.get("state") != "Completed"
        or receipt.get("receipt_type") != "completed"
        or receipt.get("cleanup_complete") is not True
        or receipt.get("failure") is not None
        or receipt.get("verification") != "verified"
    ):
        raise Unavailable(
            "fs.transfer terminal receipt does not prove a completed upload",
            reason="invalid_upload_terminal",
        )
    encoded = receipt.get("payload_base64")
    if not isinstance(encoded, str) or not encoded:
        return None
    try:
        decoded = base64.b64decode(encoded, validate=True)
        payload = json.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Unavailable(
            f"fs.transfer terminal receipt payload is invalid: {exc}",
            reason="invalid_upload_terminal",
        ) from exc
    return payload if isinstance(payload, Mapping) else None


def _require_completed_upload(
    payload: Mapping[str, object],
    *,
    expected_bytes: int,
    expected_sha256: str,
) -> None:
    if payload.get("type") == "error":
        raise Unavailable(
            f"fs.transfer rejected bundle staging: {payload.get('message') or payload}",
            reason=str(payload.get("code") or "ability_bundle_upload_failed"),
        )
    if payload.get("type") != "complete":
        raise Unavailable(
            f"fs.transfer did not complete bundle staging: {payload}",
            reason="invalid_upload_terminal",
        )
    if (
        payload.get("bytes") != expected_bytes
        or payload.get("sha256") != expected_sha256
    ):
        raise Unavailable(
            "fs.transfer completion digest does not match uploaded ability bundle",
            reason="upload_integrity_mismatch",
        )
