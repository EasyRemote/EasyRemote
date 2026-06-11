"""Client: addressing, argument mapping, dispatch, stubs, async mirror.

A FakeTransport records the exact wire dicts the client would hand to
libeasynet_cli — the assertions here pin the client half of the FFI
contract the same way test_invocation pins the codec half.
"""

import base64
import json
import time

import pytest

from easyremote.client import Client, FunctionInfo, RemoteFunction, remote
from easyremote.errors import DeadlineExceeded, InvalidArgument, Unavailable
from easyremote.identity import LocalIdentity
from easyremote.receipts import InvocationState

IDENTITY = LocalIdentity(
    realm="acme", node_id="dev-a", username="silan", hub_endpoint="hub.example:443"
)
DEVICE_URA = "easynet:///r/acme/device/dev-a"


def ok_response(result=None, content_type="application/json"):
    payload = (
        json.dumps(result).encode() if content_type == "application/json" else result
    )
    return {
        "ok": True,
        "state": int(InvocationState.COMPLETED),
        "selected_node_id": "",
        "scheduling_reason": "",
        "elapsed_ms": 1,
        "result_content_type": content_type,
        "result_base64": base64.b64encode(payload).decode() if payload else "",
        "result_json": result if content_type == "application/json" else None,
        "admission_receipt": None,
    }


class FakeTransport:
    def __init__(self, responses=None):
        self.invocations = []
        self.responses = list(responses or [])
        self.delay = 0.0

    def invoke(self, wire):
        if self.delay:
            time.sleep(self.delay)
        self.invocations.append(wire)
        return self.responses.pop(0) if self.responses else ok_response({"echo": True})


def make_client(**kwargs):
    transport = FakeTransport(**kwargs)
    client = Client(transport=transport, identity=IDENTITY)
    return client, transport


# -- identity and addressing --------------------------------------------------


def test_identity_uras_are_canonical():
    assert IDENTITY.device_ura == DEVICE_URA
    assert IDENTITY.hub_ura == "easynet:///r/acme/hub"


def test_execute_addresses_local_device_with_namespaced_ability():
    client, transport = make_client()
    client.execute("ai_inference", prompt="hi")
    wire = transport.invocations[0]
    assert wire["caller_ura"] == DEVICE_URA
    assert wire["callee_ura"] == DEVICE_URA
    assert wire["subject_ura"] == DEVICE_URA  # default subject = callee
    assert wire["ability"] == "er.ai_inference"
    assert wire["args"] == {"prompt": "hi"}
    assert wire["causal_context"] == {"form": "none"}
    assert "caller_signature" not in wire  # local-fast admission


def test_dotted_names_pass_through_and_node_targets_device():
    client, transport = make_client()
    client.call("team.fetch_sales", quarter="Q2", node="gpu-1")
    wire = transport.invocations[0]
    assert wire["ability"] == "team.fetch_sales"
    assert wire["callee_ura"] == "easynet:///r/acme/device/gpu-1"


# -- argument mapping ------------------------------------------------------------


def test_positionals_without_schema_are_rejected_with_guidance():
    client, _ = make_client()
    with pytest.raises(InvalidArgument) as exc_info:
        client.execute("fn", 1, 2)
    assert exc_info.value.reason == "parameter_order_unknown"
    assert "@remote" in str(exc_info.value)


def test_discovery_enables_positionals_and_fills_defaults():
    candidates = {
        "candidates": [
            {
                "ability": "fn",
                "qualified_name": "easynet:///r/acme/ability/user.er.fn",
                "owner": "er",
                "description": "",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer", "default": 7},
                    },
                    "x-easyremote-parameter-order": ["a", "b"],
                },
                "visibility": "device",
                "score": 1.0,
            }
        ],
        "scope": "device",
        "query": "",
    }
    client, transport = make_client(responses=[ok_response(candidates)])

    infos = client.functions()
    assert infos[0].qualified_name == "easynet:///r/acme/ability/user.er.fn"
    assert transport.invocations[0]["ability"] == "er.discover"
    assert transport.invocations[0]["args"] == {"scope": "device", "query": ""}

    client.execute("fn", 41)  # positional now mappable; default filled
    assert transport.invocations[1]["args"] == {"a": 41, "b": 7}


def test_duplicate_positional_and_keyword_rejected():
    client, _ = make_client(
        responses=[
            ok_response(
                {
                    "candidates": [
                        {
                            "ability": "fn",
                            "qualified_name": "u",
                            "owner": "er",
                            "description": "",
                            "input_schema": {
                                "properties": {"a": {}},
                                "x-easyremote-parameter-order": ["a"],
                            },
                            "visibility": "device",
                            "score": 1.0,
                        }
                    ]
                }
            )
        ]
    )
    client.functions()
    with pytest.raises(InvalidArgument, match="positionally and by keyword"):
        client.execute("fn", 1, a=2)


# -- L2 surface ---------------------------------------------------------------------


def test_prepare_inspect_adjust_send():
    client, transport = make_client()
    prepared = client.prepare("fn", x=1)
    assert prepared.tuple.subject == DEVICE_URA
    adjusted = prepared.with_subject("easynet:///r/acme/device/other")
    invocation = adjusted.send()
    assert transport.invocations[0]["subject_ura"] == "easynet:///r/acme/device/other"
    assert invocation.state is InvocationState.COMPLETED


def test_sign_true_is_honest_about_pending_path():
    client, _ = make_client()
    with pytest.raises(Unavailable) as exc_info:
        client.invoke("fn", sign=True, x=1)
    assert exc_info.value.reason == "signing_path_pending"


def test_client_wait_timeout_raises_deadline_exceeded():
    client, transport = make_client()
    transport.delay = 0.2
    with pytest.raises(DeadlineExceeded, match="timeout_seconds"):
        client.invoke("fn", x=1, timeout=0.01)


# -- @remote stub ----------------------------------------------------------------------


def test_remote_stub_binds_positionals_and_defaults_locally():
    client, transport = make_client()

    @remote(client=client)
    def ai_inference(prompt: str, max_tokens: int = 64) -> str: ...

    assert isinstance(ai_inference, RemoteFunction)
    ai_inference("hello")
    wire = transport.invocations[0]
    assert wire["ability"] == "er.ai_inference"
    assert wire["args"] == {"prompt": "hello", "max_tokens": 64}


def test_remote_stub_decorator_options():
    client, transport = make_client()

    @remote(name="custom", node="gpu-1", client=client)
    def fn(a: int) -> int: ...

    fn(5)
    wire = transport.invocations[0]
    assert wire["ability"] == "er.custom"
    assert wire["callee_ura"].endswith("/device/gpu-1")


# -- pick selection ----------------------------------------------------------


def candidate(verb, device_id):
    return {
        "ability": verb,
        "qualified_name": f"easynet:///r/acme/ability/device.{device_id}.er.{verb}",
        "owner": "device",
        "description": "",
        "input_schema": {"type": "object", "properties": {}},
        "visibility": "device",
        "score": 1.0,
    }


def test_round_robin_alternates_device_candidates():
    discover = ok_response(
        {"candidates": [candidate("fn", "dev-a"), candidate("fn", "dev-b")]}
    )
    client, transport = make_client(responses=[discover])
    client.functions()

    client.execute("fn", pick="round_robin")
    client.execute("fn", pick="round_robin")
    callees = [w["callee_ura"] for w in transport.invocations[1:]]
    assert callees == [
        "easynet:///r/acme/device/dev-a",
        "easynet:///r/acme/device/dev-b",
    ]
    assert transport.invocations[1]["ability"] == "er.fn"  # wire name from URA


def test_pick_random_chooses_a_known_candidate():
    discover = ok_response(
        {"candidates": [candidate("fn", "dev-a"), candidate("fn", "dev-b")]}
    )
    client, transport = make_client(responses=[discover])
    client.functions()
    client.execute("fn", pick="random")
    assert transport.invocations[1]["callee_ura"].rsplit("/", 1)[-1] in (
        "dev-a",
        "dev-b",
    )


def test_pick_without_candidates_falls_back_to_local():
    client, transport = make_client()
    client.execute("fn", pick="round_robin")
    assert transport.invocations[0]["callee_ura"] == DEVICE_URA


def test_agent_owned_candidates_are_skipped_by_pick():
    agent_candidate = {
        "ability": "fn",
        "qualified_name": "easynet:///r/acme/ability/user-1.claude.fn",
        "owner": "claude",
        "description": "",
        "input_schema": {},
        "visibility": "device",
        "score": 1.0,
    }
    client, transport = make_client(
        responses=[ok_response({"candidates": [agent_candidate]})]
    )
    client.functions()
    client.execute("fn", pick="round_robin")  # falls back: not addressable
    assert transport.invocations[1]["callee_ura"] == DEVICE_URA


def test_invalid_pick_policy_rejected():
    client, _ = make_client()
    with pytest.raises(InvalidArgument) as exc_info:
        client.execute("fn", pick="resource_aware")
    assert exc_info.value.reason == "invalid_pick_policy"
    assert "PR-3" in str(exc_info.value)


# -- async mirror -------------------------------------------------------------


def test_aio_mirror_executes_same_dispatch():
    import asyncio

    client, transport = make_client()
    result = asyncio.run(client.aio.execute("fn", x=1))
    assert result == {"echo": True}
    assert transport.invocations[0]["ability"] == "er.fn"


def test_function_info_parses_candidate_verbatim():
    info = FunctionInfo.from_candidate(
        {
            "ability": "weather",
            "qualified_name": "easynet:///r/acme/ability/u.claude.weather",
            "owner": "claude",
            "description": "d",
            "input_schema": {"type": "object"},
            "visibility": "device",
            "score": 0.92,
        }
    )
    assert info.name == "weather"
    assert info.owner == "claude"
    assert info.score == 0.92
