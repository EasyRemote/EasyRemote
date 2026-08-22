"""Shared fixtures."""

import base64
import hashlib
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

RuntimeReceiptFactory = Callable[..., dict[str, object]]
TEST_DESCRIPTOR_HASH = "a" * 64
TEST_DESCRIPTOR_ACTION = "invoke"


def expected_descriptor_ref(
    ability_ura: str,
    *,
    version: str = "1.0.0",
    action: str = TEST_DESCRIPTOR_ACTION,
) -> str:
    """Return the descriptor-bound ref expected from an in-memory test Runtime."""

    return f"{ability_ura}@{version}#{TEST_DESCRIPTOR_HASH}!{action}"


@pytest.fixture()
def short_tmp() -> Path:
    """A short-prefix temp dir for AF_UNIX sockets on macOS."""

    path = Path(tempfile.mkdtemp(prefix="er-", dir="/tmp"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def canonical_runtime_receipt(
    *,
    index: int = 0,
    prev_hex: str = "00" * 32,
    self_hex: str = "aa" * 32,
    **overrides: object,
) -> dict[str, object]:
    """Build a structurally complete canonical runtime receipt summary."""

    authority_payload = b"easyremote-test-authority-proof"
    receipt: dict[str, object] = {
        "index": index,
        "receipt_ura": f"easynet:///r/example/resource/test.subject/receipt/{index}",
        "invocation_id": "inv-1",
        "receipt_type": "admitted",
        "state": "admitted",
        "timestamp_unix_ms": 1_700_000_000_000,
        "prev_receipt_hash_hex": prev_hex,
        "self_hash_hex": self_hex,
        "payload_base64": "",
        "payload_content_type": "application/json",
        "cleanup_complete": False,
        "reason": "",
        "child_invocation_id": "",
        "caller_binding": {
            "ura": "easynet:///r/example/agent/test.caller",
            "profile": "axon-strict-v2",
        },
        "callee_binding": {
            "ura": "easynet:///r/example/agent/test.callee",
            "profile": "axon-strict-v2",
        },
        "subject_binding": {
            "ura": "easynet:///r/example/resource/test.subject",
            "profile": "axon-strict-v2",
        },
        "invocation_nonce_base64": base64.b64encode(bytes(range(1, 17))).decode(
            "ascii"
        ),
        "causal_binding_kind": "none",
        "causal_binding": {"form": "none"},
        "callee_signature": {
            "algorithm": "ed25519",
            "signature_base64": base64.b64encode(bytes(64)).decode("ascii"),
            "key_id_hint": "test-callee-key",
        },
        "signer_binding": {
            "ura": "easynet:///r/example/agent/test.callee",
            "profile": "axon-strict-v2",
        },
        "host_attestation_base64": "",
        "authority_binding_kind": "self+identity",
        "authority_binding": {
            "kind": "self+identity",
            "authority_ura": "easynet:///r/example/agent/test.callee",
        },
        "ability_binding": "easynet:///r/example/ability/test.runtime.execute",
        "subject_ref": {
            "kind": 1,
            "ura": "easynet:///r/example/resource/test.subject",
            "profile": "axon-strict-v2",
        },
        "descriptor_version": "1.0.0",
        "schema_hash_hex": hashlib.sha256(b"easyremote-test-schema").hexdigest(),
        "impl_hash_hex": hashlib.sha256(b"easyremote-test-impl").hexdigest(),
        "runtime_env": "python-test",
        "authority_proof": {
            "proof_type": "admission",
            "binding_kind": "self+identity",
            "binding": {
                "kind": "self+identity",
                "authority_ura": "easynet:///r/example/agent/test.callee",
            },
            "proof_payload_base64": base64.b64encode(authority_payload).decode("ascii"),
            "proof_hash_hex": hashlib.sha256(authority_payload).hexdigest(),
            "issuer": {
                "ura": "easynet:///r/example/agent/test.callee",
                "profile": "axon-strict-v2",
            },
            "signature": {
                "algorithm": "ed25519",
                "signature_base64": base64.b64encode(bytes(64)).decode("ascii"),
                "key_id_hint": "test-authority-key",
            },
            "admission_hook": "easyremote.test.admission",
        },
        "usage": {
            "tokens_in": 0,
            "tokens_out": 0,
            "duration_ms": 1,
            "external_calls": 0,
        },
        "input_hash_hex": hashlib.sha256(b"easyremote-test-input").hexdigest(),
        "output_hash_hex": hashlib.sha256(b"easyremote-test-output").hexdigest(),
        "parent_receipts": [],
    }
    receipt.update(overrides)
    return receipt


def canonical_runtime_receipt_pair() -> tuple[dict[str, object], dict[str, object]]:
    admission = canonical_runtime_receipt(
        index=0,
        self_hex="aa" * 32,
        receipt_type="admitted",
        state="Admitted",
        cleanup_complete=False,
    )
    terminal = canonical_runtime_receipt(
        index=1,
        prev_hex="aa" * 32,
        self_hex="bb" * 32,
        receipt_type="completed",
        state="Completed",
        cleanup_complete=True,
    )
    return admission, terminal


@pytest.fixture()
def runtime_receipt() -> RuntimeReceiptFactory:
    return canonical_runtime_receipt
