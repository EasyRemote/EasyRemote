"""Internal EasyRemote receipt operations use canonical SDK facts directly."""

import easynet_sdk
import pytest

from easyremote.errors import InternalError
from easyremote.receipts import (
    InvocationState,
    Receipt,
    receipt_from_mapping,
    receipt_reference,
)


def test_receipt_is_the_sdk_runtime_projection(runtime_receipt) -> None:
    receipt = receipt_from_mapping(runtime_receipt())

    assert isinstance(receipt, easynet_sdk.RuntimeReceipt)
    assert receipt.index == 0
    assert receipt.invocation_id == "inv-1"
    assert receipt.state == "admitted"
    assert receipt.prev_receipt_hash() == bytes(32)
    assert receipt.self_receipt_hash() == b"\xaa" * 32


def test_sdk_rejects_missing_proof_facts(runtime_receipt) -> None:
    value = runtime_receipt()
    value.pop("authority_proof")

    with pytest.raises(easynet_sdk.SDKError, match="authority_proof"):
        receipt_from_mapping(value)


def test_internal_receipt_decoder_rejects_unknown_lifecycle_state(
    runtime_receipt,
) -> None:
    value = runtime_receipt(state="invented_state")

    with pytest.raises(easynet_sdk.SDKError) as captured:
        receipt_from_mapping(value)

    assert captured.value.code is easynet_sdk.ErrorCode.INVALID_ARGUMENT
    assert captured.value.details["reason"] == "invalid_lifecycle_state"


def test_released_receipt_decoder_rejects_unknown_lifecycle_state(
    runtime_receipt,
) -> None:
    value = runtime_receipt(state="invented_state")

    with pytest.raises(InternalError) as captured:
        Receipt.from_wire(value)

    assert captured.value.reason == "receipt_protocol"
    assert "unknown lifecycle state" in str(captured.value)


def test_internal_receipt_decoder_rejects_missing_lifecycle_state(
    runtime_receipt,
) -> None:
    value = runtime_receipt()
    value.pop("state")

    with pytest.raises(easynet_sdk.SDKError, match="missing state"):
        receipt_from_mapping(value)


def test_released_receipt_decoder_rejects_missing_lifecycle_state(
    runtime_receipt,
) -> None:
    value = runtime_receipt()
    value.pop("state")

    with pytest.raises(InternalError) as captured:
        Receipt.from_wire(value)

    assert captured.value.reason == "receipt_protocol"
    assert "missing state" in str(captured.value)


def test_receipt_reference_uses_sdk_projection(runtime_receipt) -> None:
    receipt = receipt_from_mapping(
        runtime_receipt(
            receipt_ura=(
                "easynet:///r/example/resource/agent.easyremote.test/"
                "invocation/r-1/receipt"
            )
        )
    )

    reference = receipt_reference(receipt)

    assert reference.receipt_hash == b"\xaa" * 32
    assert reference.causal_context()["receipt_hash_hex"] == "aa" * 32


def test_invocation_state_is_the_sdk_lifecycle_type() -> None:
    assert InvocationState is easynet_sdk.InvocationLifecycleState
    assert InvocationState.COMPLETED.is_terminal
    assert not InvocationState.ADMITTED.is_terminal
