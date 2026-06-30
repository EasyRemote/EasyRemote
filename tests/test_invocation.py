"""Invocation tuple, wire codec, and response decoding.

The golden wire fixture mirrors `valid_invocation_json()` in
EasyNet-Cli/src/ffi/invocation.rs tests — if these diverge, the codec
is wrong, not the test.
"""

import base64
import json

import pytest

from easyremote.errors import InternalError, InvalidArgument
from easyremote.invocation import (
    Arguments,
    CallerSignature,
    CausalRef,
    Invocation,
    InvocationTuple,
    MerkleAnchor,
    PreparedInvocation,
    StreamSpec,
    encode_invocation,
    fresh_nonce,
)
from easyremote.receipts import InvocationState

NONCE = bytes(range(1, 17))  # base64: AQIDBAUGBwgJCgsMDQ4PEA==


def make_tuple(**overrides):
    defaults = dict(
        caller="easynet:///r/test/device/caller",
        callee="easynet:///r/test/device/callee",
        ability="observe.health",
        subject="easynet:///r/test/device/callee",
        nonce=NONCE,
        causal=None,
        arguments=Arguments.from_json({"ping": True}),
    )
    defaults.update(overrides)
    return InvocationTuple(**defaults)


# -- wire encoding -------------------------------------------------------------


def test_encode_matches_ffi_golden_fixture():
    # The golden shape is exactly what `InvocationJson::parse` reads: the
    # ability identity rides only on `descriptor_ref`. No bare `ability`
    # or `descriptor_version` field — the daemon would discard them.
    wire = encode_invocation(make_tuple())
    assert wire == {
        "caller_ura": "easynet:///r/test/device/caller",
        "callee_ura": "easynet:///r/test/device/callee",
        "descriptor_ref": (
            "easynet:///r/test/ability/device.callee.observe.health@1.0.0"
        ),
        "subject_ura": "easynet:///r/test/device/callee",
        "nonce_base64": "AQIDBAUGBwgJCgsMDQ4PEA==",
        "causal_context": {"form": "none"},
        "args": {"ping": True},
    }


def test_descriptor_version_binds_into_descriptor_ref():
    assert (
        encode_invocation(make_tuple())["descriptor_ref"]
        == "easynet:///r/test/ability/device.callee.observe.health@1.0.0"
    )
    custom = encode_invocation(make_tuple(), descriptor_version="2.3.4")
    assert (
        custom["descriptor_ref"]
        == "easynet:///r/test/ability/device.callee.observe.health@2.3.4"
    )


def test_explicit_descriptor_ref_passes_through_with_its_pinned_version():
    descriptor_ref = "easynet:///r/test/ability/device.callee.observe.health@2.3.4"
    wire = encode_invocation(make_tuple(ability=descriptor_ref))
    assert wire["descriptor_ref"] == descriptor_ref


def test_binary_arguments_use_base64_and_content_type():
    tup = make_tuple(arguments=Arguments.from_bytes(b"\x00\x01", "audio/pcm"))
    wire = encode_invocation(tup)
    assert "args" not in wire
    assert wire["arguments_base64"] == base64.b64encode(b"\x00\x01").decode()
    assert wire["content_type"] == "audio/pcm"


def test_causal_scalar_list_merkle_forms():
    ref = CausalRef(receipt_hash=b"\xab" * 32, receipt_ura="easynet:///r/x")
    scalar = encode_invocation(make_tuple(causal=ref))["causal_context"]
    assert scalar == {
        "form": "scalar",
        "receipt_hash_hex": "ab" * 32,
        "receipt_ura": "easynet:///r/x",
    }

    listed = encode_invocation(make_tuple(causal=[ref, ref]))["causal_context"]
    assert listed["form"] == "list"
    assert len(listed["prior"]) == 2

    merkle = encode_invocation(
        make_tuple(causal=MerkleAnchor(root=b"\xcd" * 32, proof_ura="easynet:///r/p"))
    )["causal_context"]
    assert merkle == {
        "form": "merkle",
        "root_hex": "cd" * 32,
        "proof_ura": "easynet:///r/p",
    }


def test_metadata_signature_and_streams_are_optional_extras():
    wire = encode_invocation(
        make_tuple(),
        metadata={"x-easynet-delegation": "producer"},
        caller_signature=CallerSignature("ed25519", b"\x07" * 64, "caller-key"),
        bidi_streams=[StreamSpec(stream_id=1, content_type="text/pty")],
    )
    assert wire["metadata"] == {"x-easynet-delegation": "producer"}
    assert wire["caller_signature"]["algorithm"] == "ed25519"
    assert (
        wire["caller_signature"]["signature_base64"]
        == base64.b64encode(b"\x07" * 64).decode()
    )
    assert wire["bidi_streams"] == [
        {
            "stream_id": 1,
            "content_type": "text/pty",
            "ordering": "STRICT",
            "codec_params": "",
        }
    ]


def test_minimal_wire_has_no_optional_keys():
    wire = encode_invocation(make_tuple())
    for key in ("metadata", "caller_signature", "bidi_streams", "content_type"):
        assert key not in wire


# -- validation -----------------------------------------------------------------


def test_nonce_contract():
    assert len(fresh_nonce()) == 16
    with pytest.raises(InvalidArgument, match="16 bytes"):
        make_tuple(nonce=b"short")
    with pytest.raises(InvalidArgument, match="all-zero"):
        make_tuple(nonce=bytes(16))


def test_empty_tuple_fields_rejected():
    with pytest.raises(InvalidArgument):
        make_tuple(ability="  ")


def test_empty_causal_list_rejected():
    with pytest.raises(InvalidArgument, match="root invocation"):
        encode_invocation(make_tuple(causal=[]))


def test_causal_ref_validates_hash_length():
    with pytest.raises(InvalidArgument, match="32 bytes"):
        CausalRef(receipt_hash=b"\x01", receipt_ura="easynet:///r/x")


def test_binary_arguments_need_content_type():
    with pytest.raises(InvalidArgument):
        Arguments.from_bytes(b"x", "  ")


def test_args_digest_is_stable_sha256():
    a = Arguments.from_json({"b": 1, "a": 2})
    b = Arguments.from_json({"b": 1, "a": 2})
    assert a.digest() == b.digest()
    assert len(a.digest()) == 32


def test_json_arguments_reject_non_finite_numbers():
    with pytest.raises(InvalidArgument) as exc_info:
        Arguments.from_json({"bad": float("nan")}).digest()
    assert exc_info.value.reason == "invalid_json_payload"


# -- response decoding ------------------------------------------------------------


def ok_response(**overrides):
    payload = {"answer": 42}
    response = {
        "ok": True,
        "state": int(InvocationState.COMPLETED),
        "selected_node_id": "node-1",
        "scheduling_reason": "direct",
        "elapsed_ms": 7,
        "result_content_type": "application/json",
        "result_base64": base64.b64encode(json.dumps(payload).encode()).decode(),
        "result_json": payload,
        "admission_receipt": None,
    }
    response.update(overrides)
    return response


def test_result_prefers_result_json():
    inv = Invocation(make_tuple(), ok_response())
    assert inv.result() == {"answer": 42}
    assert inv.state is InvocationState.COMPLETED
    assert inv.state.is_terminal
    assert inv.selected_node_id == "node-1"
    assert inv.elapsed_ms == 7


def test_result_falls_back_to_base64_json():
    inv = Invocation(make_tuple(), ok_response(result_json=None))
    assert inv.result() == {"answer": 42}


def test_binary_result_returns_bytes():
    inv = Invocation(
        make_tuple(),
        ok_response(
            result_content_type="audio/pcm",
            result_base64=base64.b64encode(b"\x01\x02").decode(),
            result_json=None,
        ),
    )
    assert inv.result() == b"\x01\x02"


def test_non_ok_response_is_a_protocol_error():
    with pytest.raises(InternalError, match="non-ok"):
        Invocation(make_tuple(), {"ok": False})


def test_receipt_absent_means_empty_chain():
    inv = Invocation(make_tuple(), ok_response())
    assert inv.receipt is None
    assert len(inv.receipts()) == 0
    assert inv.id == ""


def test_shell_executor_envelope_is_unwrapped():
    # Fixture captured live from daemon v0.64.8 (P0 closed-loop probe).
    envelope = {
        "elapsed_ms": 60,
        "exit_code": 0,
        "fulfilled_by": "shell",
        "result": '{"hello":"easynet","excited":true}',
        "sandboxed": "none",
    }
    inv = Invocation(make_tuple(), ok_response(result_json=envelope))
    assert inv.result() == {"hello": "easynet", "excited": True}
    assert inv.raw_response["result_json"] == envelope  # envelope preserved


def test_plain_text_stdout_envelope_unwraps_to_string():
    envelope = {"fulfilled_by": "shell", "exit_code": 0, "result": "plain text"}
    inv = Invocation(make_tuple(), ok_response(result_json=envelope))
    assert inv.result() == "plain text"


def test_non_envelope_dicts_pass_through():
    response = {"candidates": [], "scope": "self", "query": ""}
    inv = Invocation(make_tuple(), ok_response(result_json=response))
    assert inv.result() == response


# -- prepared invocation -----------------------------------------------------------


def test_prepared_invocation_inspect_then_send():
    sent = []

    def dispatcher(prepared):
        sent.append(prepared)
        return Invocation(prepared.tuple, ok_response())

    prepared = PreparedInvocation(tuple=make_tuple(), dispatcher=dispatcher)
    adjusted = prepared.with_subject("easynet:///r/test/device/other").with_causal(
        CausalRef(receipt_hash=b"\xee" * 32, receipt_ura="easynet:///r/r")
    )

    assert (
        prepared.tuple.subject == "easynet:///r/test/device/callee"
    )  # original untouched
    assert adjusted.tuple.subject == "easynet:///r/test/device/other"
    assert isinstance(adjusted.tuple.causal, CausalRef)

    invocation = adjusted.send()
    assert sent[0] is adjusted
    assert invocation.result() == {"answer": 42}
