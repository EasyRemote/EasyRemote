"""EasyRemote presentation over canonical SDK Invocation objects."""

import base64
import json

import easynet_sdk
import pytest
from conftest import (
    TEST_DESCRIPTOR_ACTION,
    TEST_DESCRIPTOR_HASH,
    expected_descriptor_ref,
)

from easyremote.errors import InternalError
from easyremote.invocation import Invocation

CALLER = "easynet:///r/test/user/alice"
CALLEE = "easynet:///r/test/agent/device.callee.runtime-introspection"
ABILITY = (
    "easynet:///r/test/ability/"
    "system-agent.callee.runtime-introspection.observe.health"
)
SUBJECT = "easynet:///r/test/device/callee"
NONCE = "AQIDBAUGBwgJCgsMDQ4PEA=="


def canonical_draft() -> easynet_sdk.InvocationDraft:
    addressing = easynet_sdk.AddressingClient(easynet_sdk.AxonAddressingTransport())
    invoker = easynet_sdk.AbilityInvocationClient(
        easynet_sdk.RuntimeClient(_DescriptorRuntime(addressing)),
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


class _DescriptorRuntime:
    def __init__(self, addressing: easynet_sdk.AddressingClient) -> None:
        self._addressing = addressing

    def resolve_descriptor_ref(self, request_json: bytes) -> bytes:
        request = json.loads(request_json.decode("utf-8"))
        callee_ura = str(request["callee_ura"])
        ability = str(request["ability"])
        ability_ura = (
            ability
            if ability.startswith("easynet:///")
            else self._addressing.owner_ability_ura(callee_ura, ability)
        )
        descriptor_ref = self._addressing.canonical_ability_descriptor_ref(
            ability_ura,
            "1.0.0",
            descriptor_hash=TEST_DESCRIPTOR_HASH,
            action=TEST_DESCRIPTOR_ACTION,
        )
        return json.dumps({"descriptor_ref": descriptor_ref}).encode()


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
        "terminal_state": "Completed",
        "output_content_type": output_content_type,
        "output_base64": output_base64,
        "output_json": output_json,
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
    assert draft.callee_ura == CALLEE
    assert draft.descriptor_ref == expected_descriptor_ref(ABILITY)
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


def test_accepts_top_level_sdk_runtime_result(runtime_receipt) -> None:
    draft = canonical_draft()
    response = runtime_response(
        draft,
        runtime_receipt,
        output_json={"answer": 42},
    )
    runtime_result = response["sdk_runtime_result"]
    assert isinstance(runtime_result, dict)

    invocation = Invocation.from_transport_response(runtime_result)

    assert invocation.result() == {"answer": 42}
    assert invocation.id == "inv-1"


def test_transport_response_rejects_malformed_sdk_runtime_result() -> None:
    with pytest.raises(InternalError, match="malformed"):
        Invocation.from_transport_response({"ok": True})


def test_transport_response_uses_only_sdk_owned_terminal_state(
    runtime_receipt,
) -> None:
    draft = canonical_draft()

    invocation = Invocation.from_transport_response(
        runtime_response(
            draft,
            runtime_receipt,
            state=easynet_sdk.InvocationLifecycleState.UNSPECIFIED,
        )
    )
    assert invocation.state is easynet_sdk.InvocationLifecycleState.COMPLETED

    response = runtime_response(draft, runtime_receipt)
    runtime_result = response["sdk_runtime_result"]
    assert isinstance(runtime_result, dict)
    runtime_result["terminal_state"] = "Running"
    with pytest.raises(InternalError, match="terminal_receipt state does not match"):
        Invocation.from_transport_response(response)


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
