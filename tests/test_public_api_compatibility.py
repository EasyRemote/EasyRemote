"""Released runtime-edge shapes remain available without owning runtime truth."""

from __future__ import annotations

import inspect

import easynet_sdk
import pytest

import easyremote
from easyremote.errors import Unavailable
from easyremote.invocation import (
    Arguments,
    CausalRef,
    InvocationTuple,
    MerkleAnchor,
    PreparedInvocation,
)
from easyremote.receipts import InvocationState, Receipt, ReceiptChain

CALLER = "easynet:///r/test/device/caller"
CALLEE = "easynet:///r/test/device/callee"
SUBJECT = "easynet:///r/test/resource/job-1"
RECEIPT_URA = "easynet:///r/test/resource/agent.worker/invocation/parent/receipt"
NONCE = bytes(range(1, 17))


def released_tuple(**overrides: object) -> InvocationTuple:
    values: dict[str, object] = {
        "caller": CALLER,
        "callee": CALLEE,
        "ability": "observe.health",
        "subject": SUBJECT,
        "nonce": NONCE,
        "causal": None,
        "arguments": Arguments.from_json({"ping": True}),
    }
    values.update(overrides)
    return InvocationTuple(**values)  # type: ignore[arg-type]


def test_released_constructor_shapes_are_exact() -> None:
    assert list(inspect.signature(InvocationTuple).parameters) == [
        "caller",
        "callee",
        "ability",
        "subject",
        "nonce",
        "causal",
        "arguments",
    ]
    assert list(inspect.signature(Receipt).parameters) == [
        "index",
        "invocation_id",
        "receipt_type",
        "state",
        "timestamp_unix_ms",
        "prev_receipt_hash",
        "self_hash",
        "payload_content_type",
        "cleanup_complete",
        "reason",
        "child_invocation_id",
        "raw",
    ]
    assert list(inspect.signature(ReceiptChain).parameters) == ["receipts"]
    assert list(inspect.signature(PreparedInvocation.with_causal).parameters) == [
        "self",
        "causal",
    ]


def test_released_invocation_tuple_delegates_projection_to_sdk() -> None:
    tuple_ = released_tuple()

    assert tuple_.caller == CALLER
    assert tuple_.callee == CALLEE
    assert tuple_.ability == "observe.health"
    assert tuple_.subject == SUBJECT
    assert tuple_.nonce == NONCE
    assert tuple_.causal is None
    assert tuple_.arguments == Arguments.from_json({"ping": True})
    assert isinstance(tuple_.sdk_draft, easynet_sdk.InvocationDraft)
    assert tuple_.sdk_draft.descriptor_ref.endswith(
        "/ability/device.callee.observe.health@1.0.0"
    )


def test_released_with_causal_preserves_shape_and_uses_sdk_projection() -> None:
    parent = CausalRef(receipt_hash=b"\xab" * 32, receipt_ura=RECEIPT_URA)
    prepared = PreparedInvocation(
        released_tuple(),
        dispatcher=lambda _: pytest.fail("must not dispatch"),
    )

    adjusted = prepared.with_causal(parent)

    assert isinstance(adjusted.tuple, InvocationTuple)
    assert adjusted.tuple.causal is parent
    assert adjusted.draft.causal_context == {
        "form": "scalar",
        "receipt_hash_hex": "ab" * 32,
        "receipt_ura": RECEIPT_URA,
    }


def test_released_with_causal_preserves_root_list_and_merkle_forms() -> None:
    first = CausalRef(receipt_hash=b"\x11" * 32, receipt_ura=RECEIPT_URA)
    second = CausalRef(
        receipt_hash=b"\x22" * 32,
        receipt_ura=RECEIPT_URA.replace("parent", "second"),
    )
    prepared = PreparedInvocation(
        released_tuple(),
        dispatcher=lambda _: pytest.fail("must not dispatch"),
    )

    assert prepared.with_causal(None).draft.causal_context == {"form": "none"}
    assert prepared.with_causal([first, second]).draft.causal_context == {
        "form": "list",
        "prior": [
            {
                "receipt_hash_hex": "11" * 32,
                "receipt_ura": RECEIPT_URA,
            },
            {
                "receipt_hash_hex": "22" * 32,
                "receipt_ura": RECEIPT_URA.replace("parent", "second"),
            },
        ],
    }
    assert prepared.with_causal(
        MerkleAnchor(root=b"\x33" * 32, proof_ura=RECEIPT_URA)
    ).draft.causal_context == {
        "form": "merkle",
        "root_hex": "33" * 32,
        "proof_ura": RECEIPT_URA,
    }


def test_released_receipt_fields_are_sdk_projected(runtime_receipt) -> None:
    receipt = Receipt.from_wire(runtime_receipt())

    assert receipt.index == 0
    assert receipt.invocation_id == "inv-1"
    assert receipt.receipt_type == "admitted"
    assert receipt.state is InvocationState.ADMITTED
    assert receipt.prev_receipt_hash == bytes(32)
    assert receipt.self_hash == b"\xaa" * 32
    assert receipt.payload_content_type == "application/json"
    assert receipt.cleanup_complete is False
    assert receipt.raw["self_hash_hex"] == "aa" * 32


def test_released_receipt_reference_delegates_to_sdk(runtime_receipt) -> None:
    receipt = Receipt.from_wire(runtime_receipt(receipt_ura=RECEIPT_URA))

    reference = receipt.reference()

    assert isinstance(reference, easynet_sdk.ReceiptReference)
    assert reference.receipt_ura == RECEIPT_URA
    assert reference.receipt_hash == b"\xaa" * 32


def test_released_receipt_chain_is_shape_only(runtime_receipt) -> None:
    chain = ReceiptChain([Receipt.from_wire(runtime_receipt())])

    assert len(chain) == 1
    assert chain[0].invocation_id == "inv-1"
    with pytest.raises(Unavailable) as captured:
        chain.verify_continuity()
    assert captured.value.reason == "full_receipt_chain_unavailable"


def test_released_runtime_edge_symbols_remain_top_level_exports() -> None:
    assert easyremote.InvocationTuple is InvocationTuple
    assert easyremote.Receipt is Receipt
    assert easyremote.ReceiptChain is ReceiptChain
