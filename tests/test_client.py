"""Client: addressing, argument mapping, dispatch, stubs, async mirror.

A FakeTransport records the exact wire dicts the client would hand to
libeasynet_cli — the assertions here pin the client half of the FFI
contract the same way test_invocation pins the codec half.
"""

import base64
import json
import time

import pytest

from easyremote.client import Client, FunctionInfo, RemoteFunction, Stream, remote
from easyremote.errors import (
    DeadlineExceeded,
    InternalError,
    InvalidArgument,
    Unavailable,
)
from easyremote.identity import LocalIdentity
from easyremote.receipts import InvocationState
from easyremote.schema import PARAMETER_ORDER_KEY, VAR_POSITIONAL_KEY

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


class _FakeFrames:
    """A stream of host_stream chunk frames + a terminal frame, built
    from an `ok_response`-shaped result so `Stream` can drain it."""

    def __init__(self, result):
        encoded_null = "bnVsbA==" if result is None else None
        self._frames = [
            {
                "payload_json": result,
                "payload_base64": encoded_null,
                "content_type": "application/json",
                "terminal": False,
                "error": None,
            },
            {
                "payload_json": None,
                "payload_base64": None,
                "terminal": True,
                "error": None,
            },
        ]
        self.closed = False

    def __iter__(self):
        return iter(self._frames)

    def close(self):
        self.closed = True


class _FakeBidi:
    def __init__(self):
        self.sent = []
        self.closed = False
        self.cancelled = False

    def send(self, frame):
        self.sent.append(frame)

    def recv(self, timeout=None):
        return None

    def close(self):
        self.closed = True

    def cancel(self):
        self.cancelled = True


class FakeTransport:
    def __init__(self, responses=None):
        self.invocations = []
        self.responses = list(responses or [])
        self.delay = 0.0
        self.closed = False
        self.bidi_channel = None

    def invoke(self, wire):
        if self.delay:
            time.sleep(self.delay)
        self.invocations.append(wire)
        return self.responses.pop(0) if self.responses else ok_response({"echo": True})

    def stream(self, wire):
        # execute/call now drain a host_stream; record the wire (same
        # assertions as the old invoke path) and yield the ability result
        # as a single chunk frame followed by terminal. Queued responses
        # are `ok_response(...)` envelopes (for the legacy invoke shape);
        # a real host_stream frame carries only the ability's result, so
        # unwrap `result_json` to mirror that.
        if self.delay:
            time.sleep(self.delay)
        self.invocations.append(wire)
        response = self.responses.pop(0) if self.responses else {"echo": True}
        if isinstance(response, dict) and "result_json" in response:
            result = response["result_json"]
        else:
            result = response
        return _FakeFrames(result)

    def bidi(self, wire):
        if self.delay:
            time.sleep(self.delay)
        self.invocations.append(wire)
        self.bidi_channel = _FakeBidi()
        return self.bidi_channel

    def close(self):
        self.closed = True


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
    client.call(Client.target("team.fetch_sales", node="gpu-1"), quarter="Q2")
    wire = transport.invocations[0]
    assert wire["ability"] == "team.fetch_sales"
    assert wire["callee_ura"] == "easynet:///r/acme/device/gpu-1"


def test_ability_ura_is_handed_to_daemon_invoke_without_python_route_derivation():
    ability_ura = "easynet:///r/acme/ability/device.gpu-1.team.fetch_sales"
    client, transport = make_client(
        responses=[
            ok_response(
                {
                    "result": {"rows": 3},
                    "fulfilled_by": "registry_dispatch",
                    "target": "easynet:///r/acme/device/gpu-1",
                    "ability": "team.fetch_sales",
                    "qualified_name": ability_ura,
                }
            )
        ]
    )

    result = client.call(ability_ura, quarter="Q2")

    assert result == {"rows": 3}
    wire = transport.invocations[0]
    assert wire["callee_ura"] == DEVICE_URA
    assert wire["subject_ura"] == ability_ura
    assert wire["ability"] == "er.invoke"
    assert wire["args"] == {
        "ability_ura": ability_ura,
        "args": {"quarter": "Q2"},
    }


def test_agent_owned_ability_ura_uses_same_daemon_invoke_path():
    ability_ura = "easynet:///r/acme/ability/user-1.claude.weather"
    client, transport = make_client(
        responses=[
            ok_response({"result": "sunny", "fulfilled_by": "registry_dispatch"})
        ]
    )

    assert client.call(ability_ura, city="Singapore") == "sunny"
    assert transport.invocations[0]["ability"] == "er.invoke"
    assert transport.invocations[0]["args"] == {
        "ability_ura": ability_ura,
        "args": {"city": "Singapore"},
    }


def test_ability_ura_cannot_be_combined_with_python_targeting():
    client, _ = make_client()
    with pytest.raises(InvalidArgument) as exc_info:
        client.call(
            Client.target(
                "easynet:///r/acme/ability/user-1.claude.weather",
                node="gpu-1",
            )
        )
    assert exc_info.value.reason == "target_override_for_ability_ura"


def test_ability_ura_stream_rejects_until_cli_exposes_stream_surface():
    client, _ = make_client()
    with pytest.raises(Unavailable) as exc_info:
        client.stream("easynet:///r/acme/ability/user-1.claude.weather")
    assert exc_info.value.reason == "ability_ura_stream_surface_missing"


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


def test_discovery_maps_surplus_positionals_to_varargs():
    client, transport = make_client()
    client._schemas["fn"] = {
        "type": "object",
        "properties": {
            "base": {"type": "integer"},
            "nums": {"type": "array", "items": {"type": "integer"}},
        },
        PARAMETER_ORDER_KEY: ["base", "nums"],
        VAR_POSITIONAL_KEY: "nums",
    }

    client.execute("fn", 10, 1, 2, 3)

    assert transport.invocations[0]["args"] == {"base": 10, "nums": [1, 2, 3]}


def test_discovery_rejects_varargs_duplicate():
    client, _ = make_client()
    client._schemas["fn"] = {
        "type": "object",
        "properties": {"nums": {"type": "array"}},
        PARAMETER_ORDER_KEY: ["nums"],
        VAR_POSITIONAL_KEY: "nums",
    }

    with pytest.raises(InvalidArgument, match="positionally and by keyword"):
        client.execute("fn", 1, 2, nums=[3])


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
        client.invoke(Client.target("fn", sign=True), x=1)
    assert exc_info.value.reason == "signing_path_pending"


def test_client_wait_timeout_raises_deadline_exceeded():
    client, transport = make_client()
    transport.delay = 0.2
    started = time.perf_counter()
    with pytest.raises(DeadlineExceeded, match="timeout_seconds"):
        client.invoke(Client.target("fn", timeout=0.01), x=1)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.1, "client-side deadline must bound caller wait time"


def test_context_manager_exit_after_timeout_is_bounded(monkeypatch):
    first = FakeTransport()
    first.delay = 0.2
    monkeypatch.setattr("easyremote.client.Transport.connect", lambda: first)

    started = time.perf_counter()
    with pytest.raises(DeadlineExceeded), Client(identity=IDENTITY) as client:
        client.invoke(Client.target("fn", timeout=0.01), x=1)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.1, "Client.__exit__ must not wait for retired C calls"

    deadline = time.perf_counter() + 1.0
    while not first.closed and time.perf_counter() < deadline:
        time.sleep(0.01)
    assert first.closed


def test_timed_out_owned_transport_is_not_reused(monkeypatch):
    first = FakeTransport()
    second = FakeTransport()
    first.delay = 0.2
    transports = [first, second]

    def connect():
        return transports.pop(0)

    monkeypatch.setattr("easyremote.client.Transport.connect", connect)
    client = Client(identity=IDENTITY)

    with pytest.raises(DeadlineExceeded):
        client.invoke(Client.target("fn", timeout=0.01), x=1)

    client.invoke(Client.target("fn", timeout=1.0), x=2)
    assert len(transports) == 0

    # The first handle is retired immediately and closed once its still-running
    # C call returns; the second call must open and use a fresh handle.
    deadline = time.perf_counter() + 1.0
    while not first.closed and time.perf_counter() < deadline:
        time.sleep(0.01)
    assert first.closed
    assert client._transport is second


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


def test_remote_stub_business_args_can_use_control_names():
    client, transport = make_client()

    @remote(client=client)
    def echo(node: str, pick: str, timeout: int) -> dict: ...

    echo("business-node", "business-pick", 7)
    wire = transport.invocations[0]
    assert wire["callee_ura"] == DEVICE_URA
    assert wire["args"] == {
        "node": "business-node",
        "pick": "business-pick",
        "timeout": 7,
    }


def test_remote_stub_lowers_bytes_before_json_transport():
    client, transport = make_client()

    @remote(client=client)
    def make_thumbnail(image: bytes, size: int = 64) -> bytes: ...

    make_thumbnail(image=b"\x00\x01\x02", size=2)
    wire = transport.invocations[0]
    json.dumps(wire)  # would fail if bytes leaked into the transport dict
    assert wire["args"] == {"image": "AAEC", "size": 2}


def test_remote_stub_invoke_rejects_host_stream_ability():
    client, _ = make_client()

    @remote(client=client)
    def fn(a: int) -> int: ...

    with pytest.raises(Unavailable) as exc_info:
        fn.invoke(1)
    assert exc_info.value.reason == "host_stream_invoke_not_supported"


# -- pick selection ----------------------------------------------------------


def candidate(verb, device_id, schema=None):
    return {
        "ability": verb,
        "qualified_name": f"easynet:///r/acme/ability/device.{device_id}.er.{verb}",
        "owner": "device",
        "description": "",
        "input_schema": schema or {"type": "object", "properties": {}},
        "visibility": "device",
        "score": 1.0,
    }


def test_round_robin_alternates_device_candidates():
    discover = ok_response(
        {"candidates": [candidate("fn", "dev-a"), candidate("fn", "dev-b")]}
    )
    client, transport = make_client(responses=[discover])
    client.functions()

    client.execute(Client.target("fn", pick="round_robin"))
    client.execute(Client.target("fn", pick="round_robin"))
    selected = [w["args"]["ability_ura"] for w in transport.invocations[1:]]
    assert selected == [
        "easynet:///r/acme/ability/device.dev-a.er.fn",
        "easynet:///r/acme/ability/device.dev-b.er.fn",
    ]
    assert transport.invocations[1]["callee_ura"] == DEVICE_URA
    assert transport.invocations[1]["ability"] == "er.invoke"


def test_pick_random_chooses_a_known_candidate():
    discover = ok_response(
        {"candidates": [candidate("fn", "dev-a"), candidate("fn", "dev-b")]}
    )
    client, transport = make_client(responses=[discover])
    client.functions()
    client.execute(Client.target("fn", pick="random"))
    assert transport.invocations[1]["args"]["ability_ura"] in (
        "easynet:///r/acme/ability/device.dev-a.er.fn",
        "easynet:///r/acme/ability/device.dev-b.er.fn",
    )


def test_pick_uses_selected_candidate_schema_for_positionals():
    schema_a = {
        "type": "object",
        "properties": {"x": {"type": "integer"}},
        PARAMETER_ORDER_KEY: ["x"],
    }
    schema_b = {
        "type": "object",
        "properties": {"y": {"type": "integer"}},
        PARAMETER_ORDER_KEY: ["y"],
    }
    discover = ok_response(
        {
            "candidates": [
                candidate("fn", "dev-b", schema_a),
                candidate("fn", "dev-c", schema_b),
            ]
        }
    )
    client, transport = make_client(responses=[discover])
    client.functions()

    with pytest.raises(InvalidArgument) as exc_info:
        client.execute("fn", 1)
    assert exc_info.value.reason == "parameter_order_unknown"

    client.execute(Client.target("fn", pick="round_robin"), 11)
    client.execute(Client.target("fn", pick="round_robin"), 22)

    assert transport.invocations[1]["args"]["args"] == {"x": 11}
    assert transport.invocations[2]["args"]["args"] == {"y": 22}


def test_discovery_does_not_cache_schema_when_candidate_omits_schema():
    schema = {
        "type": "object",
        "properties": {"x": {"type": "integer"}},
        PARAMETER_ORDER_KEY: ["x"],
    }
    missing_schema = {
        "ability": "fn",
        "qualified_name": "easynet:///r/acme/ability/device.dev-c.er.fn",
        "owner": "device",
        "description": "",
        "visibility": "device",
        "score": 1.0,
    }
    discover = ok_response(
        {"candidates": [candidate("fn", "dev-b", schema), missing_schema]}
    )
    client, _ = make_client(responses=[discover])
    client.functions()

    with pytest.raises(InvalidArgument) as exc_info:
        client.execute("fn", 1)
    assert exc_info.value.reason == "parameter_order_unknown"


def test_pick_without_candidates_falls_back_to_local():
    client, transport = make_client()
    client.execute(Client.target("fn", pick="round_robin"))
    assert transport.invocations[0]["callee_ura"] == DEVICE_URA


def test_agent_owned_candidates_are_pickable_without_python_ura_parsing():
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
    client.execute(Client.target("fn", pick="round_robin"))
    assert transport.invocations[1]["ability"] == "er.invoke"
    assert (
        transport.invocations[1]["args"]["ability_ura"]
        == agent_candidate["qualified_name"]
    )


def test_invalid_pick_policy_rejected():
    client, _ = make_client()
    with pytest.raises(InvalidArgument) as exc_info:
        client.execute(Client.target("fn", pick="resource_aware"))
    assert exc_info.value.reason == "invalid_pick_policy"
    assert "PR-3" in str(exc_info.value)


# -- async mirror -------------------------------------------------------------


def test_aio_mirror_executes_same_dispatch():
    import asyncio

    client, transport = make_client()
    result = asyncio.run(client.aio.execute("fn", x=1))
    assert result == {"echo": True}
    assert transport.invocations[0]["ability"] == "er.fn"


def test_aio_mirror_exposes_prepare_stream_and_session():
    import asyncio

    client, transport = make_client()

    prepared = asyncio.run(client.aio.prepare("fn", x=1))
    assert prepared.tuple.ability == "er.fn"
    assert prepared.tuple.arguments.json_value == {"x": 1}

    stream = asyncio.run(client.aio.stream("fn", x=2))
    assert list(stream) == [{"echo": True}]
    assert transport.invocations[0]["ability"] == "er.fn"

    session = asyncio.run(client.aio.session("fn", x=3))
    assert transport.invocations[1]["ability"] == "er.fn"
    assert transport.invocations[1]["bidi_streams"][0]["stream_id"] == 0
    session.send({"payload": "hi"})
    assert transport.bidi_channel.sent == [{"payload": "hi"}]
    session.close()
    assert transport.bidi_channel.closed


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


# -- Stream frame iteration ---------------------------------------------------


class FakeFrameStream:
    """Minimal stand-in for the transport FrameStream: a fixed list of
    chunk-envelope dicts plus a closed flag, so Stream's iteration logic
    is testable without libeasynet_cli or a daemon."""

    def __init__(self, frames):
        self._frames = frames
        self.closed = False

    def __iter__(self):
        return iter(self._frames)

    def close(self):
        self.closed = True


def chunk(payload_json=None, *, terminal=False, error=None):
    return {
        "payload_json": payload_json,
        "payload_base64": "bnVsbA==" if payload_json is None and not terminal else None,
        "content_type": "application/json",
        "terminal": terminal,
        "error": error,
    }


class TimeoutFrameStream:
    def __init__(self):
        self.closed = False

    def recv(self, timeout=None):
        raise TimeoutError("blocked")

    def close(self):
        self.closed = True


def test_stream_yields_values_then_stops_on_terminal():
    fs = FakeFrameStream(
        [chunk("a"), chunk("b"), chunk("c"), chunk(None, terminal=True)]
    )
    assert list(Stream(fs)) == ["a", "b", "c"]
    assert fs.closed, "stream must close the transport on exhaustion"


def test_stream_empty_terminates_cleanly():
    fs = FakeFrameStream([chunk(None, terminal=True)])
    assert list(Stream(fs)) == []
    assert fs.closed


def test_stream_preserves_json_null_payload():
    fs = FakeFrameStream([chunk(None), chunk(None, terminal=True)])
    assert list(Stream(fs)) == [None]


def test_stream_decodes_non_json_payload_bytes():
    fs = FakeFrameStream(
        [
            {
                "payload_json": None,
                "payload_base64": "AAE=",
                "content_type": "application/octet-stream",
                "terminal": False,
                "error": None,
            },
            chunk(None, terminal=True),
        ]
    )

    assert list(Stream(fs)) == [b"\x00\x01"]


def test_stream_idle_timeout_closes_and_raises_deadline():
    fs = TimeoutFrameStream()
    with pytest.raises(DeadlineExceeded, match="no stream frame"):
        list(Stream(fs, timeout=0.01))
    assert fs.closed


def test_stream_yields_heterogeneous_json_values():
    fs = FakeFrameStream(
        [
            chunk({"k": 1}),
            chunk([1, 2, 3]),
            chunk("s"),
            chunk(42),
            chunk(None, terminal=True),
        ]
    )
    assert list(Stream(fs)) == [{"k": 1}, [1, 2, 3], "s", 42]


def test_stream_raises_on_host_propagated_error_frame():
    # A raised generator surfaces as a single {"error": {...}} payload.
    err = {
        "error": {"kind": "INTERNAL", "reason": "function_raised", "message": "boom"}
    }
    fs = FakeFrameStream([chunk(0), chunk(1), chunk(err)])
    out = []
    with pytest.raises(InternalError, match="boom"):
        for v in Stream(fs):
            out.append(v)
    assert out == [0, 1], "values before the error are still delivered"
    assert fs.closed


def test_stream_does_not_mistake_user_data_containing_error_field():
    # Ordinary output that merely has an `error` key must pass through —
    # only the exact single-key {"error": {kind:...}} shape is a failure.
    payload = {"error": {"detail": "this is data, no kind"}, "ok": True}
    fs = FakeFrameStream([chunk(payload), chunk(None, terminal=True)])
    assert list(Stream(fs)) == [payload]


def test_stream_raises_on_envelope_error():
    fs = FakeFrameStream(
        [chunk("a"), chunk(None, error={"kind": "UNAVAILABLE", "message": "down"})]
    )
    out = []
    with pytest.raises(Unavailable, match="down"):
        for v in Stream(fs):
            out.append(v)
    assert out == ["a"]
