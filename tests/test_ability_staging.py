"""Ability bundle staging state and receipt gates."""

import base64
import io
import json
import tarfile

import easynet_sdk
import pytest

from easyremote._ability_staging import (
    _ability_bundle_archive,
    _require_completed_upload,
    _upload_completion_payload,
)
from easyremote.errors import InvalidArgument, Unavailable


def _terminal_frame(payload: object, *, verification: str = "verified"):
    return easynet_sdk.BidiFrame(
        sequence=2,
        kind="receipt",
        terminal=True,
        terminal_receipt={
            "state": "Completed",
            "receipt_type": "completed",
            "cleanup_complete": True,
            "failure": None,
            "verification": verification,
            "payload_base64": base64.b64encode(json.dumps(payload).encode()).decode(),
        },
    )


def test_bundle_archive_contains_only_root_manifest(tmp_path):
    package = tmp_path / "ability"
    package.mkdir()
    (package / "ability.json").write_text('{"name":"ping"}')
    (package / "caller-owned.txt").write_text("not part of runtime manifest")

    encoded = _ability_bundle_archive(package)

    with tarfile.open(fileobj=io.BytesIO(encoded), mode="r:gz") as archive:
        assert archive.getnames() == ["ability.json"]
        assert archive.extractfile("ability.json").read() == b'{"name":"ping"}'


def test_bundle_archive_requires_manifest(tmp_path):
    with pytest.raises(InvalidArgument) as exc_info:
        _ability_bundle_archive(tmp_path)

    assert exc_info.value.reason == "ability_manifest_missing"


def test_verified_terminal_receipt_projects_completion_payload():
    payload = {"type": "complete", "bytes": 7, "sha256": "abc"}

    assert _upload_completion_payload(_terminal_frame(payload)) == payload


def test_unverified_terminal_receipt_cannot_complete_upload():
    with pytest.raises(Unavailable) as exc_info:
        _upload_completion_payload(
            _terminal_frame({"type": "complete"}, verification="unverified")
        )

    assert exc_info.value.reason == "invalid_upload_terminal"


def test_completion_digest_must_match_uploaded_archive():
    with pytest.raises(Unavailable) as exc_info:
        _require_completed_upload(
            {"type": "complete", "bytes": 6, "sha256": "wrong"},
            expected_bytes=7,
            expected_sha256="expected",
        )

    assert exc_info.value.reason == "upload_integrity_mismatch"
