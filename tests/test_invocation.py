"""EasyRemote presentation over canonical SDK Invocation objects."""

import base64
from typing import cast

import easynet_sdk
import pytest

from easyremote.errors import InternalError, InvalidArgument
from easyremote.invocation import Invocation, PreparedInvocation

CALLER = "easynet:///r/test/device/caller"
ABILITY = "easynet:///r/test/ability/device.callee.observe.health"
SUBJECT = "easynet:///r/test/device/callee"
NONCE = "AQIDBAUGBwgJCgsMDQ4PEA=="


def canonical_draft() -> easynet_sdk.InvocationDraft:
    addressing = easynet_sdk.AddressingClient(easynet_sdk.AxonAddressingTransport())
    invoker = easynet_sdk.AbilityInvocationClient(
        cast(easynet_sdk.RuntimeClient, object()),
        addressing,
    )
    try:
        return invoker.build_target_invocation(
            easynet_sdk.AbilityTargetRequest(
                caller_ura=CALLER,
                ability_ura=ABILITY,
                subject_ura=SUBJECT,
                nonce_base64=NONCE,
                causal_context={"form": "none"},
                args={"ping": True},
            )
        )
    finally:
        addressing.close()


def runtime_response(
    draft: easynet_sdk.InvocationDraft,
    runtime_receipt,
    *,
    output_json=None,
    output_content_type: str = "application/json",
    output_base64: str = "",
    admission_receipt=None,
    terminal_receipt=None,
    state: easynet_sdk.InvocationLifecycleState = (
        easynet_sdk.InvocationLifecycleState.COMPLETED
    ),
):
    if admission_receipt is None and terminal_receipt is None:
        admission_receipt = runtime_receipt(
            index=0,
            receipt_type="admitted",
            state="Admitted",
            cleanup_complete=False,
        )
        terminal_receipt = runtime_receipt(
            index=1,
            prev_hex=admission_receipt["self_hash_hex"],
            receipt_type="completed",
            state="Completed",
            cleanup_complete=True,
        )
    runtime_result = {
        "ok": True,
        "tuple": draft.to_json_dict(),
        "invocation_id": "inv-1",
        "terminal_state": "completed",
        "output_content_type": output_content_type,
        "output_base64": output_base64,
        "output_json": output_json,
        "selected_node_id": "node-1",
        "scheduling_reason": "direct",
        "elapsed_ms": 7,
        "admission_receipt": admission_receipt,
        "terminal_receipt": terminal_receipt,
        "error": None,
    }
    return {
        "ok": True,
        "state": int(state),
        "sdk_runtime_result": runtime_result,
    }


def test_sdk_provider_owns_complete_invocation_draft() -> None:
    draft = canonical_draft()

    assert draft.caller_ura == CALLER
    assert draft.callee_ura == "easynet:///r/test/device/callee"
    assert draft.descriptor_ref == f"{ABILITY}@1.0.0"
    assert draft.subject_ura == SUBJECT
    assert draft.nonce_base64 == NONCE
    assert draft.causal_context == {"form": "none"}
    assert draft.args == {"ping": True}


def test_product_result_unwraps_executor_envelope(runtime_receipt) -> None:
    draft = canonical_draft()
    invocation = Invocation.from_transport_response(
        runtime_response(
            draft,
            runtime_receipt,
            output_json={
                "fulfilled_by": "shell",
                "exit_code": 0,
                "result": '{"answer":42}',
            },
        )
    )

    assert invocation.result() == {"answer": 42}
    assert invocation.tuple is not draft
    assert invocation.tuple.to_json_dict() == draft.to_json_dict()
    assert invocation.state is easynet_sdk.InvocationLifecycleState.COMPLETED
    assert invocation.selected_node_id == "node-1"


def test_product_result_decodes_binary_output(runtime_receipt) -> None:
    draft = canonical_draft()
    invocation = Invocation.from_transport_response(
        runtime_response(
            draft,
            runtime_receipt,
            output_content_type="audio/pcm",
            output_base64=base64.b64encode(b"\x01\x02").decode("ascii"),
        )
    )

    assert invocation.result() == b"\x01\x02"


def test_transport_response_requires_sdk_runtime_result() -> None:
    with pytest.raises(InternalError, match="sdk_runtime_result"):
        Invocation.from_transport_response({"ok": True})


def test_transport_response_rejects_unknown_or_nonterminal_state(
    runtime_receipt,
) -> None:
    draft = canonical_draft()

    with pytest.raises(InternalError, match="non-terminal Invocation state"):
        Invocation.from_transport_response(
            runtime_response(
                draft,
                runtime_receipt,
                state=easynet_sdk.InvocationLifecycleState.UNSPECIFIED,
            )
        )


def test_prepared_invocation_adjustments_round_trip_through_sdk(
    runtime_receipt,
) -> None:
    sent = []

    def dispatch(prepared):
        sent.append(prepared.draft)
        return Invocation.from_transport_response(
            runtime_response(
                prepared.draft,
                runtime_receipt,
                output_json={"answer": 42},
            )
        )

    prepared = PreparedInvocation(draft=canonical_draft(), dispatcher=dispatch)
    adjusted = prepared.with_subject("easynet:///r/test/device/other").with_causal(
        {"form": "none"}
    )

    assert prepared.draft.subject_ura == SUBJECT
    assert adjusted.draft.subject_ura == "easynet:///r/test/device/other"
    assert adjusted.send().result() == {"answer": 42}
    assert sent == [adjusted.draft]


def test_prepared_invocation_rejects_invalid_sdk_adjustment() -> None:
    prepared = PreparedInvocation(
        draft=canonical_draft(),
        dispatcher=lambda _: pytest.fail("must not dispatch"),
    )

    with pytest.raises(InvalidArgument):
        prepared.with_subject("")


def test_transport_response_rejects_incomplete_receipt_proof(
    runtime_receipt,
) -> None:
    response = runtime_response(canonical_draft(), runtime_receipt)
    runtime_result = response["sdk_runtime_result"]
    assert isinstance(runtime_result, dict)
    terminal = runtime_result["terminal_receipt"]
    assert isinstance(terminal, dict)
    terminal.pop("authority_proof")

    with pytest.raises(InternalError, match="authority_proof"):
        Invocation.from_transport_response(response)
