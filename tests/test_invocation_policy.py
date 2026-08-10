"""EasyRemote product derivation policies emit canonical SDK request DTOs."""

from typing import Any, cast

import easynet_sdk
import pytest

from easyremote.errors import InvalidArgument
from easyremote.invocation_policy import (
    ChildCausal,
    CompleteExplicit,
    ExplicitSubject,
    FreshRoot,
    ResolvedTargetSubject,
)

NONCE_BASE64 = "AQIDBAUGBwgJCgsMDQ4PEA=="
CALLER = "easynet:///r/test/user/alice"
ABILITY = "easynet:///r/test/ability/alice.worker.jobs.run"
SUBJECT = "easynet:///r/test/resource/job-1"
RESOLVED_SUBJECT = ABILITY
RECEIPT_URA = "easynet:///r/test/resource/agent.callee/invocation/inv-1/receipt"


def request(policy):
    return policy.request(
        caller_ura=CALLER,
        ability_ura=ABILITY,
        resolved_subject_ura=RESOLVED_SUBJECT,
        args={"job": 1},
        metadata={"trace": "test"},
    )


def test_complete_explicit_preserves_canonical_fields() -> None:
    value = request(
        CompleteExplicit(
            subject_ura=SUBJECT,
            nonce_base64=NONCE_BASE64,
            causal_context={"form": "none"},
        )
    )

    assert isinstance(value, easynet_sdk.AbilityTargetRequest)
    assert value.subject_ura == SUBJECT
    assert value.nonce_base64 == NONCE_BASE64
    assert value.causal_context == {"form": "none"}


def test_complete_explicit_missing_field_fails_closed() -> None:
    constructor = cast(Any, CompleteExplicit)

    with pytest.raises(TypeError):
        constructor(subject_ura=SUBJECT, nonce_base64=NONCE_BASE64)


def test_fresh_root_uses_sdk_nonce_and_declares_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        easynet_sdk,
        "new_invocation_nonce_base64",
        lambda: NONCE_BASE64,
    )

    value = request(FreshRoot(ExplicitSubject(SUBJECT)))

    assert value.subject_ura == SUBJECT
    assert value.nonce_base64 == NONCE_BASE64
    assert value.causal_context == {"form": "none"}


def test_resolved_target_subject_is_explicit_product_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        easynet_sdk,
        "new_invocation_nonce_base64",
        lambda: NONCE_BASE64,
    )

    value = request(FreshRoot(ResolvedTargetSubject()))

    assert value.subject_ura == RESOLVED_SUBJECT


def test_child_causal_uses_sdk_receipt_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        easynet_sdk,
        "new_invocation_nonce_base64",
        lambda: NONCE_BASE64,
    )
    parent = easynet_sdk.ReceiptReference(
        receipt_ura=RECEIPT_URA,
        receipt_hash=b"\xab" * 32,
    )

    value = request(
        ChildCausal(
            subject=ExplicitSubject(SUBJECT),
            parent=parent,
        )
    )

    assert value.causal_context == {
        "form": "scalar",
        "receipt_hash_hex": "ab" * 32,
        "receipt_ura": RECEIPT_URA,
    }


def test_child_causal_rejects_missing_parent_reference() -> None:
    with pytest.raises(InvalidArgument) as exc_info:
        request(
            ChildCausal(
                subject=ExplicitSubject(SUBJECT),
                parent=cast(Any, None),
            )
        )

    assert exc_info.value.reason == "invalid_parent_receipt_reference"
