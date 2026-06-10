"""Receipt summaries: parsing, chain continuity, honest verify()."""

import pytest

from easyremote.errors import InternalError, Unavailable
from easyremote.receipts import InvocationState, Receipt, ReceiptChain


def wire_receipt(index=0, prev_hex="00" * 32, self_hex="aa" * 32, **overrides):
    wire = {
        "index": index,
        "invocation_id": "inv-1",
        "receipt_type": 1,
        "state": int(InvocationState.ADMITTED),
        "timestamp_unix_ms": 1_700_000_000_000,
        "prev_receipt_hash_hex": prev_hex,
        "self_hash_hex": self_hex,
        "payload_content_type": "application/json",
        "cleanup_complete": False,
        "reason": "",
        "child_invocation_id": "",
    }
    wire.update(overrides)
    return wire


def test_from_wire_parses_all_fields():
    receipt = Receipt.from_wire(wire_receipt())
    assert receipt.index == 0
    assert receipt.invocation_id == "inv-1"
    assert receipt.state is InvocationState.ADMITTED
    assert receipt.prev_receipt_hash == bytes(32)
    assert receipt.self_hash == b"\xaa" * 32
    assert receipt.raw["self_hash_hex"] == "aa" * 32  # nothing lost


def test_unknown_state_degrades_to_unspecified_not_crash():
    receipt = Receipt.from_wire(wire_receipt(state=999))
    assert receipt.state is InvocationState.UNSPECIFIED
    assert receipt.raw["state"] == 999


def test_malformed_summary_is_protocol_error():
    with pytest.raises(InternalError, match="malformed"):
        Receipt.from_wire({"index": "zero"})


def test_verify_is_honest_about_the_abi_gap():
    with pytest.raises(Unavailable) as exc_info:
        Receipt.from_wire(wire_receipt()).verify()
    assert exc_info.value.reason == "full_receipt_unavailable"


def test_chain_continuity_holds():
    first = Receipt.from_wire(wire_receipt(index=0, self_hex="aa" * 32))
    second = Receipt.from_wire(
        wire_receipt(index=1, prev_hex="aa" * 32, self_hex="bb" * 32)
    )
    ReceiptChain([first, second]).verify_continuity()  # no raise


def test_chain_break_is_reported_with_index():
    first = Receipt.from_wire(wire_receipt(index=0, self_hex="aa" * 32))
    second = Receipt.from_wire(
        wire_receipt(index=1, prev_hex="cc" * 32, self_hex="bb" * 32)
    )
    with pytest.raises(InternalError) as exc_info:
        ReceiptChain([first, second]).verify_continuity()
    assert exc_info.value.reason == "receipt_chain_broken"
    assert "index 1" in str(exc_info.value)


def test_terminal_states():
    terminal = {
        InvocationState.COMPLETED,
        InvocationState.FAILED,
        InvocationState.TIMED_OUT,
        InvocationState.CANCELLED,
    }
    for state in InvocationState:
        assert state.is_terminal == (state in terminal)
