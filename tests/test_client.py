"""Client: addressing, argument mapping, dispatch, stubs, async mirror.

A FakeTransport records the exact wire dicts the client hands to the SDK
transport facade. The assertions here pin the client half of the daemon
Invocation contract the same way test_invocation pins the codec half.
"""

import base64
import inspect
import json
import time
from typing import Any, cast

import easynet_sdk
import pytest
from axon_sdk.invocation import parse_invocation_trace_graph
from conftest import (
    TEST_DESCRIPTOR_ACTION,
    TEST_DESCRIPTOR_HASH,
    canonical_runtime_receipt_pair,
    expected_descriptor_ref,
)
from easynet_sdk import InvocationLifecycleState as InvocationState

from easyremote.agent import RemoteAgent
from easyremote.client import (
    BidiSession,
    Client,
    FunctionInfo,
    RemoteAbility,
    RemoteDevice,
    RemoteFunction,
    RemoteOwner,
    Stream,
    remote,
)
from easyremote.errors import (
    DeadlineExceeded,
    InternalError,
    InvalidArgument,
    Unavailable,
)
from easyremote.identity import LocalIdentity
from easyremote.invocation_policy import (
    CompleteExplicit,
    FreshRoot,
    InvocationDerivationPolicy,
    ResolvedTargetSubject,
)
from easyremote.mission import MissionControl
from easyremote.schema import PARAMETER_ORDER_KEY, VAR_POSITIONAL_KEY

IDENTITY = LocalIdentity(
    realm="acme", node_id="dev-a", username="silan", hub_endpoint="hub.example:443"
)
DEVICE_URA = "easynet:///r/acme/device/dev-a"
USER_URA = "easynet:///r/acme/user/silan"
ABILITY_MANAGER_URA = (
    "easynet:///r/acme/agent/device.dev-a.ability-management"
)
INTROSPECTION_URA = (
    "easynet:///r/acme/agent/device.dev-a.runtime-introspection"
)
RUNTIME_STATE_SUBJECT = (
    "easynet:///r/acme/resource/user.silan/runtime-state/read"
)
UUID_AGENT_OWNER_URA = (
    "easynet:///r/acme/agent/"
    "019fb758-94a8-7441-acd1-55280797b9a90.claude-code"
)
UUID_AGENT_CHAT_URA = (
    "easynet:///r/acme/ability/"
    "019fb758-94a8-7441-acd1-55280797b9a90.claude-code.chat"
)
NONCE = bytes(range(1, 17))


def ok_response(result=None, content_type="application/json"):
    payload = (
        json.dumps(result).encode() if content_type == "application/json" else result
    )
    admission, terminal = canonical_runtime_receipt_pair()
    return {
        "ok": True,
        "state": int(InvocationState.COMPLETED),
        "elapsed_ms": 1,
        "result_content_type": content_type,
        "result_base64": base64.b64encode(payload).decode() if payload else "",
        "result_json": result if content_type == "application/json" else None,
        "admission_receipt": admission,
        "terminal_receipt": terminal,
    }


def agent_catalogue_response(owner_ura: str = UUID_AGENT_OWNER_URA):
    return ok_response(
        {
            "abilities": [
                {
                    "name": "chat",
                    "ability_ura": UUID_AGENT_CHAT_URA,
                    "owner_ura": owner_ura,
                    "description": "Agent chat",
                    "input_schema": {},
                }
            ]
        }
    )


def empty_catalogue_response():
    return ok_response({"abilities": []})


def native_agent_trace(request_id="inv-1", state="completed"):
    return parse_invocation_trace_graph(
        {
            "trace_id": "trace-agent-1",
            "records": [
                {
                    "invocation_ura": (
                        "easynet:///r/acme/resource/device.dev-a/invocation/"
                        f"{request_id}/history"
                    ),
                    "request_id": request_id,
                    "trace_id": "trace-agent-1",
                    "span_id": "span-agent-1",
                    "caller_ura": DEVICE_URA,
                    "callee_ura": "easynet:///r/acme/agent/silan.claude-code",
                    "subject_ura": (
                        "easynet:///r/acme/resource/device.dev-a/benchmark/"
                        "invocation-subject/subject-hash"
                    ),
                    "ability_ura": "easynet:///r/acme/ability/silan.claude-code.chat",
                    "ability_name": "chat",
                    "state": state,
                    "started_unix_ms": 1,
                    "completed_unix_ms": 2,
                    "elapsed_ms": 1,
                    "args": {},
                    "result": None,
                    "error": None,
                    "diagnostics": [],
                    "causal_links": [],
                    "receipt_chain": {},
                    "visibility": {},
                    "authority_form": "self",
                    "usage": {
                        "tokens_in": 7,
                        "tokens_out": 3,
                        "duration_ms": 1,
                        "external_calls": 0,
                    },
                }
            ],
            "edges": [],
        }
    )


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
    def __init__(self, *, frames=None, timeout=False):
        self.sent = []
        self.closed = False
        self.cancelled = False
        self.cancel_reason = ""
        self.frames = list(frames or [])
        self.timeout = timeout

    def send(self, frame):
        self.sent.append(frame)

    def recv(self, timeout=None):
        if self.timeout:
            raise TimeoutError("no frame")
        if self.frames:
            return self.frames.pop(0)
        return None

    def close(self):
        self.closed = True

    def cancel(self, reason=""):
        self.cancelled = True
        self.cancel_reason = reason


class _FakeDescriptorResolver:
    def __init__(self, addressing: easynet_sdk.AddressingClient) -> None:
        self._addressing = addressing
        self.requests: list[dict[str, Any]] = []
        self.close_calls = 0

    def resolve_descriptor_ref(self, request_json: bytes) -> bytes:
        request = json.loads(request_json.decode("utf-8"))
        self.requests.append(request)
        callee_ura = str(request.get("callee_ura") or "").strip()
        ability = str(request.get("ability") or "").strip()
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
        return json.dumps(
            {"descriptor_ref": descriptor_ref},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def close(self) -> None:
        self.close_calls += 1


class FakeTransport:
    def __init__(self, responses=None, traces=None):
        self.invocations = []
        self.carriers = []
        self.signers = []
        self.responses = list(responses or [])
        self.traces = list(traces or [])
        self.trace_requests = []
        self.descriptor_requests = []
        self.delay = 0.0
        self.closed = False
        self.bidi_channel = None
        self._addressing = easynet_sdk.AddressingClient(
            easynet_sdk.AxonAddressingTransport()
        )
        self._descriptor_resolver = _FakeDescriptorResolver(self._addressing)
        self._invoker = easynet_sdk.AbilityInvocationClient(
            easynet_sdk.RuntimeClient(self._descriptor_resolver),
            self._addressing,
        )

    def build_invocation(self, request):
        return (
            easynet_sdk.InvocationBuilder()
            .with_caller_ura(request.caller_ura)
            .with_callee_ura(request.callee_ura)
            .with_descriptor_ref(request.descriptor_ref)
            .with_subject_ura(request.subject_ura)
            .with_nonce_base64(request.nonce_base64)
            .with_causal_context(request.causal_context)
            .with_content_type(request.content_type)
            .with_metadata(dict(request.metadata))
            .with_json_args(request.args)
            .build()
        )

    def get_ability_descriptor(
        self,
        call,
        *,
        ability_ura,
        call_mode="",
        descriptor_version="",
        scope="",
    ):
        self.descriptor_requests.append(
            {
                "call": call,
                "ability_ura": ability_ura,
                "call_mode": call_mode,
                "descriptor_version": descriptor_version,
                "scope": scope,
            }
        )
        projection = self._addressing.project_ability_ura(ability_ura)
        return {
            "name": str(projection.public_name),
            "ability_ura": ability_ura,
            "descriptor_ref": expected_descriptor_ref(ability_ura),
            "owner_ura": str(projection.owner_ura),
            "descriptor_version": descriptor_version or "1.0.0",
            "call_mode": call_mode,
            "input_schema": {},
            "metadata": {},
        }

    def invoke_runtime_ability(self, call, ability_name, arguments):
        response = (
            self.responses.pop(0) if self.responses else ok_response({"abilities": []})
        )
        result = response.get("result_json") if isinstance(response, dict) else response
        if (
            isinstance(result, dict)
            and "candidates" in result
            and "abilities" not in result
        ):
            result = {"abilities": result["candidates"]}
        descriptor_action = (
            "read" if ability_name == "meta.list_abilities" else "invoke"
        )
        ability_ura = self._addressing.owner_ability_ura(call.callee_ura, ability_name)
        descriptor_ref = self._addressing.canonical_ability_descriptor_ref(
            ability_ura,
            call.descriptor_version or "1.0.0",
            descriptor_hash=TEST_DESCRIPTOR_HASH,
            action=descriptor_action,
        )
        self.invocations.append(
            {
                "descriptor_ref": descriptor_ref,
                "caller_ura": call.caller_ura,
                "callee_ura": call.callee_ura,
                "subject_ura": call.subject_ura,
                "args": arguments,
            }
        )
        self.carriers.append("runtime")
        return result

    def list_ability_descriptors(
        self,
        call,
        *,
        scope="",
        owner_ura="",
        ability_ura="",
    ):
        args = {}
        if scope:
            args["scope"] = scope
        if owner_ura:
            args["owner_ura"] = owner_ura
        if ability_ura:
            args["ability_ura"] = ability_ura
        result = self.invoke_runtime_ability(call, "meta.list_abilities", args)
        rows = result.get("abilities") if isinstance(result, dict) else None
        return rows if isinstance(rows, list) else []

    def invocation_trace(self, call, *, request_id):
        self.trace_requests.append({"call": call, "request_id": request_id})
        if not self.traces:
            raise AssertionError("no fake invocation trace queued")
        return self.traces.pop(0)

    def invoke(self, draft):
        if self.delay:
            time.sleep(self.delay)
        wire = draft.to_json_dict()
        self.invocations.append(wire)
        self.carriers.append("unary")
        response = (
            self.responses.pop(0) if self.responses else ok_response({"echo": True})
        )
        return self._canonical_response(draft, response)

    def invoke_signed(self, draft, *, signer=None, options=None):
        _ = options
        if signer is None:
            raise easynet_sdk.SDKError(
                code=easynet_sdk.ErrorCode.NOT_IMPLEMENTED,
                stage="easyremote_signing",
                retry=easynet_sdk.RetryHint.NEVER,
                retryable=False,
                message=(
                    "EasyRemote signed invocation requires a daemon-authorized "
                    "SDK Signer"
                ),
                details={"reason": "signing_path_pending"},
            )
        if self.delay:
            time.sleep(self.delay)
        wire = draft.to_json_dict()
        self.invocations.append(wire)
        self.carriers.append("signed")
        self.signers.append(signer)
        response = (
            self.responses.pop(0) if self.responses else ok_response({"echo": True})
        )
        return self._canonical_response(draft, response)

    def stream(self, draft):
        # execute/call now drain a host_stream; record the wire (same
        # assertions as the old invoke path) and yield the ability result
        # as a single chunk frame followed by terminal. Queued responses
        # are `ok_response(...)` envelopes (for the legacy invoke shape);
        # a real host_stream frame carries only the ability's result, so
        # unwrap `result_json` to mirror that.
        if self.delay:
            time.sleep(self.delay)
        wire = draft.to_json_dict()
        self.invocations.append(wire)
        self.carriers.append("stream")
        response = self.responses.pop(0) if self.responses else {"echo": True}
        if isinstance(response, dict) and "result_json" in response:
            result = response["result_json"]
        else:
            result = response
        return _FakeFrames(result)

    def bidi(self, draft, streams=()):
        if self.delay:
            time.sleep(self.delay)
        wire = draft.to_json_dict()
        self.streams = tuple(streams)
        self.invocations.append(wire)
        self.carriers.append("bidi")
        self.bidi_channel = _FakeBidi()
        return self.bidi_channel

    def close(self):
        self.closed = True
        self._addressing.close()

    @staticmethod
    def _canonical_response(draft, response):
        value = dict(response)
        value["sdk_runtime_result"] = {
            "ok": True,
            "tuple": draft.to_json_dict(),
            "invocation_id": "inv-1",
            "terminal_state": "Completed",
            "output_content_type": value.get("result_content_type", ""),
            "output_base64": value.get("result_base64", ""),
            "output_json": value.get("result_json"),
            "elapsed_ms": value.get("elapsed_ms", 0),
            "admission_receipt": value.get("admission_receipt"),
            "terminal_receipt": value.get("terminal_receipt"),
            "error": None,
        }
        return value


class RouteNegativeTransport(FakeTransport):
    def invoke(self, draft):
        wire = draft.to_json_dict()
        self.invocations.append(wire)
        self.carriers.append("unary")
        raise InternalError(
            "easynet_invocation_invoke: daemon returned gRPC status for"
            f" {wire['descriptor_ref']}: code=FailedPrecondition,"
            " message=ROUTE_NEGATIVE: namespace.resolve negative",
            reason="protocol",
        )


def make_client(**kwargs):
    signer = kwargs.pop("signer", None)
    invocation_policy = kwargs.pop(
        "invocation_policy",
        FreshRoot(ResolvedTargetSubject()),
    )
    transport = FakeTransport(**kwargs)
    client = Client(
        transport=transport,
        identity=IDENTITY,
        signer=signer,
        invocation_policy=invocation_policy,
    )
    return client, transport


def fake_signer():
    class _StaticSignatureProvider:
        def sign(self, material, handle):
            _ = material
            return easynet_sdk.InvocationSignature(
                algorithm=handle.algorithm,
                signature_base64="c2lnbmF0dXJl",
                key_id_hint=handle.signer_id,
            )

    handle = easynet_sdk.SignerHandle(
        profile="identity",
        signer_id="signer-dev-a",
        owner_ura=DEVICE_URA,
        key_id="dev-a-key",
        algorithm="ed25519",
        policy={},
        metadata={},
    )
    return easynet_sdk.Signer(handle=handle, provider=_StaticSignatureProvider())


# -- identity and addressing --------------------------------------------------


def test_identity_uras_are_canonical():
    assert IDENTITY.device_ura == DEVICE_URA
    assert IDENTITY.hub_ura == "easynet:///r/acme/authority"


def test_explicit_root_policy_uses_user_and_ability_management_system_agent():
    client, transport = make_client()
    client.execute("ai_inference", prompt="hi")
    wire = transport.invocations[0]
    assert wire["caller_ura"] == USER_URA
    assert wire["callee_ura"] == ABILITY_MANAGER_URA
    assert wire["subject_ura"] == easynet_sdk.owner_ability_ura(
        ABILITY_MANAGER_URA, "er.ai_inference"
    )
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        easynet_sdk.owner_ability_ura(ABILITY_MANAGER_URA, "er.ai_inference")
    )
    assert wire["args"] == {"prompt": "hi"}
    assert wire["causal_context"] == {"form": "none"}
    assert "caller_signature" not in wire  # local-fast admission


def test_dotted_names_pass_through_and_device_selector_projects_ability_manager():
    client, transport = make_client()
    client.call(
        Client.target("team.fetch_sales", node="gpu-1"),
        quarter="Q2",
    )
    wire = transport.invocations[0]
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.gpu-1.ability-management.team.fetch_sales"
    )
    assert wire["callee_ura"] == (
        "easynet:///r/acme/agent/device.gpu-1.ability-management"
    )


def test_obsolete_device_owned_ability_ura_is_rejected():
    ability_ura = "easynet:///r/acme/ability/device.gpu-1.team.fetch_sales"
    client, transport = make_client(responses=[ok_response({"rows": 3})])

    with pytest.raises(InvalidArgument) as exc_info:
        client.call(ability_ura, quarter="Q2")
    assert exc_info.value.reason == "device_is_not_ability_owner"
    assert transport.invocations == []


def test_agent_owned_ability_ura_uses_same_daemon_invoke_path():
    ability_ura = "easynet:///r/acme/ability/user-1.claude.weather"
    client, transport = make_client(
        responses=[
            ok_response({"result": "sunny", "fulfilled_by": "registry_dispatch"})
        ]
    )

    assert client.call(ability_ura, city="Singapore") == "sunny"
    assert transport.carriers == ["unary"]
    assert (
        transport.invocations[0]["callee_ura"]
        == "easynet:///r/acme/agent/user-1.claude"
    )
    assert transport.invocations[0]["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/user-1.claude.weather"
    )
    assert transport.invocations[0]["args"] == {"city": "Singapore"}


def test_owner_ura_namespace_projects_short_function_to_ability_ura():
    owner_ura = "easynet:///r/acme/agent/dev.caesura"
    transport = FakeTransport(responses=[ok_response("ok")])
    client = Client(
        namespace=owner_ura,
        transport=transport,
        identity=IDENTITY,
        invocation_policy=FreshRoot(ResolvedTargetSubject()),
    )

    assert client.call("discover", query="") == "ok"

    wire = transport.invocations[0]
    assert wire["callee_ura"] == owner_ura
    assert wire["subject_ura"] == "easynet:///r/acme/ability/dev.caesura.discover"
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/dev.caesura.discover"
    )
    assert wire["args"] == {"query": ""}


def test_dotted_namespace_does_not_read_local_agent_registry(monkeypatch, tmp_path):
    home = tmp_path / "home"
    state = home / ".easynet"
    state.mkdir(parents=True)
    (state / "local-agents.json").write_text(
        json.dumps(
            {
                "hosted_agents": [
                    {
                        "name": "caesura",
                        "agent_ura": "easynet:///r/acme/agent/dev.caesura",
                    }
                ]
            }
        )
    )
    monkeypatch.setenv("HOME", str(home))
    client, transport = make_client()

    client.invoke("caesura.discover", scope="self", query="")

    wire = transport.invocations[0]
    assert wire["callee_ura"] == ABILITY_MANAGER_URA
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.dev-a.ability-management.caesura.discover"
    )


def test_ability_ura_cannot_be_combined_with_python_targeting():
    client, _ = make_client()
    with pytest.raises(InvalidArgument) as exc_info:
        client.call(
            Client.target(
                "easynet:///r/acme/ability/user-1.claude.weather",
                node="gpu-1",
            ),
        )
    assert exc_info.value.reason == "target_override_for_ability_ura"


def test_route_negative_surfaces_without_cli_subprocess_retry():
    transport = RouteNegativeTransport()
    client = Client(
        transport=transport,
        identity=IDENTITY,
        invocation_policy=FreshRoot(ResolvedTargetSubject()),
    )

    with pytest.raises(InternalError) as exc_info:
        client.invoke("observe.health")

    assert exc_info.value.reason == "protocol"
    assert len(transport.invocations) == 1


def test_ability_ura_stream_uses_descriptor_bound_stream_surface():
    ability_ura = "easynet:///r/acme/ability/user-1.claude.weather"
    client, transport = make_client(responses=[ok_response("sunny")])

    assert list(client.stream(ability_ura, city="Singapore")) == ["sunny"]
    wire = transport.invocations[0]
    assert wire["callee_ura"] == "easynet:///r/acme/agent/user-1.claude"
    assert wire["subject_ura"] == ability_ura
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/user-1.claude.weather"
    )


def test_ability_ura_bidi_uses_descriptor_bound_bidi_surface():
    ability_ura = "easynet:///r/acme/ability/user-1.claude.terminal"
    client, transport = make_client()

    session = client.session(ability_ura, command="bash")

    assert transport.bidi_channel is not None
    session.close()
    wire = transport.invocations[0]
    assert wire["callee_ura"] == "easynet:///r/acme/agent/user-1.claude"
    assert wire["subject_ura"] == ability_ura
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/user-1.claude.terminal"
    )


def test_bidi_session_close_releases_without_claiming_cancellation():
    channel = _FakeBidi()
    session = BidiSession(easynet_sdk.BidiSessionAdapter(channel))

    session.close()

    assert not channel.cancelled
    assert channel.closed


def test_bidi_cancel_waits_for_sdk_terminal_receipt_without_local_close():
    terminal_receipt = {"invocation_id": "inv-bidi-1", "index": 2}
    channel = _FakeBidi(
        frames=[
            {
                "terminal": True,
                "terminal_receipt": terminal_receipt,
            }
        ]
    )
    session = BidiSession(easynet_sdk.BidiSessionAdapter(channel))

    session.cancel("user stop")
    terminal = session.recv(timeout=0.1)

    assert channel.cancelled
    assert channel.cancel_reason == "user stop"
    assert not channel.closed
    assert terminal == {
        "terminal": True,
        "terminal_receipt": terminal_receipt,
    }


def test_bidi_timeout_and_disconnect_consume_sdk_terminal_semantics():
    timed_out = BidiSession(easynet_sdk.BidiSessionAdapter(_FakeBidi(timeout=True)))
    with pytest.raises(DeadlineExceeded) as raised:
        timed_out.recv(timeout=0.01)
    assert raised.value.reason == "client_wait_timeout"

    disconnected_channel = _FakeBidi()
    disconnected = BidiSession(easynet_sdk.BidiSessionAdapter(disconnected_channel))
    assert disconnected.recv(timeout=0.01) is None
    assert not disconnected_channel.cancelled
    assert not disconnected_channel.closed


def test_bidi_remote_transport_failure_maps_without_product_state_inference():
    channel = _FakeBidi(
        frames=[
            {
                "terminal": False,
                "transport_terminal": True,
                "error": {
                    "kind": "UNAVAILABLE",
                    "message": "peer disconnected",
                },
            }
        ]
    )
    session = BidiSession(easynet_sdk.BidiSessionAdapter(channel))

    with pytest.raises(Unavailable, match="peer disconnected"):
        session.recv(timeout=0.1)

    assert not channel.cancelled


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
                "ability_ura": "easynet:///r/acme/ability/user.er.fn",
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
    assert infos[0].ability_ura == "easynet:///r/acme/ability/user.er.fn"
    assert infos[0].qualified_name == "easynet:///r/acme/ability/user.er.fn"
    assert transport.invocations[0]["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.dev-a.runtime-introspection.meta.list_abilities",
        action="read",
    )
    assert transport.invocations[0]["args"] == {}

    client.execute("fn", 41)  # positional now mappable; default filled
    assert transport.invocations[1]["args"] == {"a": 41, "b": 7}


def test_functions_with_owner_ura_namespace_discovers_canonical_owner():
    owner_ura = "easynet:///r/acme/agent/dev.caesura"
    transport = FakeTransport(
        responses=[
            ok_response(
                {
                    "candidates": [
                        {
                            "ability": "fn",
                            "qualified_name": "easynet:///r/acme/ability/dev.caesura.fn",
                            "owner": "caesura",
                            "description": "",
                            "input_schema": {},
                            "visibility": "device",
                            "score": 1.0,
                        }
                    ]
                }
            )
        ],
    )
    client = Client(namespace=owner_ura, transport=transport, identity=IDENTITY)

    infos = client.functions(scope="self")

    assert infos[0].qualified_name == "easynet:///r/acme/ability/dev.caesura.fn"
    wire = transport.invocations[0]
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.dev-a.runtime-introspection.meta.list_abilities",
        action="read",
    )
    assert wire["args"] == {}


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


def _seed_verb_schema(client, verb, schema):
    """Populate the discovery cache with one SystemAgent-owned verb schema."""
    client._addressing.cache.replace(
        [FunctionInfo.from_candidate(candidate(verb, "dev-a", schema))]
    )


def test_discovery_maps_surplus_positionals_to_varargs():
    client, transport = make_client()
    _seed_verb_schema(
        client,
        "fn",
        {
            "type": "object",
            "properties": {
                "base": {"type": "integer"},
                "nums": {"type": "array", "items": {"type": "integer"}},
            },
            PARAMETER_ORDER_KEY: ["base", "nums"],
            VAR_POSITIONAL_KEY: "nums",
        },
    )

    client.execute("fn", 10, 1, 2, 3)

    assert transport.invocations[0]["args"] == {"base": 10, "nums": [1, 2, 3]}


def test_discovery_rejects_varargs_duplicate():
    client, _ = make_client()
    _seed_verb_schema(
        client,
        "fn",
        {
            "type": "object",
            "properties": {"nums": {"type": "array"}},
            PARAMETER_ORDER_KEY: ["nums"],
            VAR_POSITIONAL_KEY: "nums",
        },
    )

    with pytest.raises(InvalidArgument, match="positionally and by keyword"):
        client.execute("fn", 1, 2, nums=[3])


# -- L2 surface ---------------------------------------------------------------------


def test_public_invocation_method_shapes_do_not_expose_policy_parameters():
    client, _ = make_client()
    mirrors = (client, client.aio)

    for mirror in mirrors:
        for method_name in ("execute", "call", "stream", "invoke", "prepare"):
            parameters = inspect.signature(getattr(mirror, method_name)).parameters
            assert parameters["function"].kind is inspect.Parameter.POSITIONAL_ONLY
            assert parameters["args"].kind is inspect.Parameter.VAR_POSITIONAL
            assert parameters["kwargs"].kind is inspect.Parameter.VAR_KEYWORD
            assert "policy" not in parameters

        session_parameters = inspect.signature(mirror.session).parameters
        assert session_parameters["function"].kind is inspect.Parameter.POSITIONAL_ONLY
        assert session_parameters["kwargs"].kind is inspect.Parameter.VAR_KEYWORD
        assert "policy" not in session_parameters


def test_client_exposes_only_an_explicit_read_only_product_policy():
    policy = FreshRoot(ResolvedTargetSubject())
    client, _ = make_client(invocation_policy=policy)

    assert client.invocation_policy is policy
    with pytest.raises(AttributeError):
        client.invocation_policy = policy  # type: ignore[misc]


def test_client_without_policy_fails_closed_before_sdk_request_construction():
    transport = FakeTransport()
    client = Client(transport=transport, identity=IDENTITY)

    with pytest.raises(InvalidArgument) as exc_info:
        client.prepare("fn", x=1)

    assert exc_info.value.reason == "missing_invocation_derivation_policy"
    assert transport.invocations == []


def test_prepare_preserves_complete_explicit_derivation():
    policy = CompleteExplicit(
        subject_ura="easynet:///r/acme/resource/job-1",
        nonce_base64=base64.b64encode(NONCE).decode("ascii"),
        causal_context={"form": "none"},
    )
    transport = FakeTransport()
    client = Client(
        transport=transport,
        identity=IDENTITY,
        invocation_policy=policy,
    )

    prepared = client.prepare("fn", x=1)

    assert client.invocation_policy is policy
    assert prepared.tuple.subject_ura == "easynet:///r/acme/resource/job-1"
    assert prepared.tuple.nonce_base64 == base64.b64encode(NONCE).decode("ascii")
    assert prepared.tuple.causal_context == {"form": "none"}


def test_target_policy_overrides_client_policy():
    client_policy = CompleteExplicit(
        subject_ura="easynet:///r/acme/resource/client-default",
        nonce_base64=base64.b64encode(NONCE).decode("ascii"),
        causal_context={"form": "none"},
    )
    target_policy = CompleteExplicit(
        subject_ura="easynet:///r/acme/resource/target-override",
        nonce_base64=base64.b64encode(NONCE[::-1]).decode("ascii"),
        causal_context={"form": "none"},
    )
    transport = FakeTransport()
    client = Client(
        transport=transport,
        identity=IDENTITY,
        invocation_policy=client_policy,
    )

    prepared = client.prepare(
        Client.target("fn", invocation_policy=target_policy),
        x=1,
    )

    assert prepared.tuple.subject_ura.endswith("/target-override")
    assert prepared.tuple.nonce_base64 == base64.b64encode(NONCE[::-1]).decode("ascii")


def test_target_surface_contains_no_legacy_tuple_derivation_fields():
    parameters = inspect.signature(Client.target).parameters

    assert "subject" not in parameters
    assert "causal" not in parameters
    assert "invocation_policy" in parameters


def test_policy_keyword_is_forwarded_as_an_ability_argument():
    client, transport = make_client()

    client.execute("fn", policy={"mode": "ability-owned"})

    assert transport.invocations[0]["args"] == {"policy": {"mode": "ability-owned"}}


def test_invalid_or_underspecified_policies_fail_before_dispatch():
    transport = FakeTransport()
    with pytest.raises(InvalidArgument) as exc_info:
        Client(
            transport=transport,
            identity=IDENTITY,
            invocation_policy=cast(Any, object()),
        )
    assert exc_info.value.reason == "invalid_invocation_derivation_policy"

    with pytest.raises(InvalidArgument) as exc_info:
        Client.target("fn", invocation_policy=cast(Any, object()))
    assert exc_info.value.reason == "invalid_invocation_derivation_policy"

    client, transport = make_client()
    target = Client.target(
        "fn",
        invocation_policy=FreshRoot(cast(Any, None)),
    )
    with pytest.raises(InvalidArgument) as exc_info:
        client.prepare(target, x=1)
    assert exc_info.value.reason == "invalid_invocation_subject_policy"
    assert transport.invocations == []


def test_policy_must_produce_an_sdk_request_before_dispatch():
    class InvalidPolicy(InvocationDerivationPolicy):
        def request(self, **kwargs: object) -> easynet_sdk.AbilityTargetRequest:
            del kwargs
            return cast(Any, None)

    client, transport = make_client()
    target = Client.target("fn", invocation_policy=InvalidPolicy())

    with pytest.raises(InvalidArgument) as exc_info:
        client.prepare(target, x=1)

    assert exc_info.value.reason == "invalid_invocation_derivation_policy"
    assert transport.invocations == []


def test_sign_true_is_honest_about_pending_path():
    client, _ = make_client()
    prepared = client.prepare(Client.target("fn", sign=True), x=1)
    assert prepared.sign is True

    with pytest.raises(Unavailable) as exc_info:
        prepared.send()
    assert exc_info.value.reason == "signing_path_pending"


def test_sign_true_uses_sdk_signed_dispatch_when_signer_is_configured():
    signer = fake_signer()
    client, transport = make_client(signer=signer)

    invocation = client.invoke(Client.target("fn", sign=True), x=1)

    assert invocation.result() == {"echo": True}
    assert transport.carriers == ["signed"]
    assert transport.signers == [signer]
    expected_suffix = f".er.fn@1.0.0#{TEST_DESCRIPTOR_HASH}!{TEST_DESCRIPTOR_ACTION}"
    assert transport.invocations[0]["descriptor_ref"].endswith(expected_suffix)
    assert "caller_signature" not in transport.invocations[0]


def test_invalid_client_timeouts_are_rejected_at_facade_boundary():
    with pytest.raises(InvalidArgument) as exc_info:
        Client(timeout=0)
    assert exc_info.value.reason == "invalid_timeout"

    with pytest.raises(InvalidArgument) as exc_info:
        Client.target("fn", timeout=-1)
    assert exc_info.value.reason == "invalid_timeout"


def test_client_wait_timeout_raises_deadline_exceeded():
    client, transport = make_client()
    transport.delay = 0.2
    started = time.perf_counter()
    with pytest.raises(DeadlineExceeded, match="timeout_seconds") as exc_info:
        client.invoke(Client.target("fn", timeout=0.01), x=1)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.1, "client-side deadline must bound caller wait time"
    assert exc_info.value.reason == "client_wait_timeout"


def test_context_manager_exit_after_timeout_is_bounded(monkeypatch):
    first = FakeTransport()
    first.delay = 0.2
    monkeypatch.setattr("easyremote.client.Transport.connect", lambda: first)

    started = time.perf_counter()
    with (
        pytest.raises(DeadlineExceeded),
        Client(
            identity=IDENTITY,
            invocation_policy=FreshRoot(ResolvedTargetSubject()),
        ) as client,
    ):
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
    client = Client(
        identity=IDENTITY,
        invocation_policy=FreshRoot(ResolvedTargetSubject()),
    )

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
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.ai_inference"
    )
    assert wire["args"] == {"prompt": "hello", "max_tokens": 64}


def test_remote_stub_decorator_options():
    client, transport = make_client()

    @remote(name="custom", node="gpu-1", client=client)
    def fn(a: int) -> int: ...

    fn(5)
    wire = transport.invocations[0]
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.gpu-1.ability-management.er.custom"
    )
    assert wire["callee_ura"] == (
        "easynet:///r/acme/agent/device.gpu-1.ability-management"
    )


def test_remote_stub_business_args_can_use_control_names():
    client, transport = make_client()

    @remote(client=client)
    def echo(node: str, pick: str, timeout: int) -> dict: ...

    echo("business-node", "business-pick", 7)
    wire = transport.invocations[0]
    assert wire["callee_ura"] == ABILITY_MANAGER_URA
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


def test_remote_stub_invoke_uses_descriptor_public_rpc_mode():
    client, transport = make_client()

    @remote(client=client)
    def fn(a: int) -> int: ...

    invocation = fn.invoke(1)

    assert invocation.state.is_terminal
    assert transport.carriers == ["unary"]


# -- @remote as a descriptor (the property playbook) ---------------------------


def test_remote_descriptor_on_class_strips_self():
    client, transport = make_client()

    class GPUCluster:
        def __init__(self, c):
            self.client = c

        @remote
        def ai_inference(self, prompt: str, max_tokens: int = 64) -> str: ...

    GPUCluster(client).ai_inference("hello")
    wire = transport.invocations[0]
    # The host instance never reaches the wire; only business args do.
    assert wire["args"] == {"prompt": "hello", "max_tokens": 64}
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.ai_inference"
    )


def test_remote_descriptor_uses_declared_name():
    client, transport = make_client()

    class Cluster:
        def __init__(self, c):
            self.client = c

        @remote  # no name= → __set_name__ adopts "ai_inference"
        def ai_inference(self, prompt: str) -> str: ...

    Cluster(client).ai_inference("hi")
    assert transport.invocations[0]["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.ai_inference"
    )


def test_remote_descriptor_explicit_name_wins_over_attribute():
    client, transport = make_client()

    class Cluster:
        def __init__(self, c):
            self.client = c

        @remote(name="custom")
        def ai_inference(self, prompt: str) -> str: ...

    Cluster(client).ai_inference("hi")
    assert transport.invocations[0]["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.custom"
    )


def test_remote_descriptor_resolves_client_from_instance():
    client, transport = make_client()

    class Cluster:
        def __init__(self, c):
            self._client = c  # the ._client fallback

        @remote
        def fn(self, a: int) -> int: ...

    Cluster(client).fn(5)
    assert transport.invocations[0]["args"] == {"a": 5}


def test_remote_descriptor_class_access_returns_descriptor():
    class Cluster:
        @remote
        def fn(self, a: int) -> int: ...

    assert isinstance(Cluster.fn, RemoteFunction)


def test_remote_descriptor_binding_is_cached_per_instance():
    client, _ = make_client()

    class Cluster:
        def __init__(self, c):
            self.client = c

        @remote
        def fn(self, a: int) -> int: ...

    host = Cluster(client)
    assert host.fn is host.fn  # same bound object across accesses


def test_remote_descriptor_explicit_client_overrides_instance():
    explicit, explicit_tx = make_client()
    other, other_tx = make_client()

    class Cluster:
        def __init__(self, c):
            self.client = c

        @remote(client=explicit)
        def fn(self, a: int) -> int: ...

    Cluster(other).fn(1)
    assert len(explicit_tx.invocations) == 1
    assert len(other_tx.invocations) == 0


def test_remote_descriptor_supports_stream():
    client, transport = make_client()

    class Cluster:
        def __init__(self, c):
            self.client = c

        @remote
        def gen(self, n: int) -> int: ...

    list(Cluster(client).gen(3))
    assert transport.invocations[0]["args"] == {"n": 3}


# -- owner handles (symmetric to @node.register) -------------------------------


def test_agent_handle_remote_addresses_agent_owner():
    client, transport = make_client()

    alice = client.agent("u-alice.chatbot")

    @alice.remote
    def chat(prompt: str) -> str: ...

    chat("hi")
    wire = transport.invocations[0]
    assert wire["callee_ura"] == "easynet:///r/acme/agent/u-alice.chatbot"
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/u-alice.chatbot.er.chat"
    )
    assert wire["args"] == {"prompt": "hi"}


def test_bare_agent_handle_binds_paired_user_and_returns_agent_profile():
    client, _ = make_client()

    handle = client.agent("claude-code")

    assert isinstance(handle, RemoteAgent)
    assert handle.name == "claude-code"
    assert handle.owner_ura == "easynet:///r/acme/agent/silan.claude-code"


def test_agent_chat_preserves_benchmark_messages_and_joins_native_trace():
    response = ok_response(
        {
            "reply": "MATCH (c:Case) RETURN count(c)",
            "tool_calls": [],
            "usage": {"input_tokens": 7, "output_tokens": 3},
            "elapsed_ms": 1,
            "session_id": "unused-strict-session",
        }
    )
    client, transport = make_client(
        responses=[agent_catalogue_response(), response],
        traces=[native_agent_trace()],
    )
    messages = [
        {"role": "system", "content": "Return only SIGNAL."},
        {"role": "user", "content": "Count all cases."},
    ]

    result = client.agent("claude-code").chat(
        messages=messages,
        subject="benchmark://enterprise_knowledge_text2signal/case-1",
        execution={"cwd": "benchmarks/run-1/case-1", "timeout_ms": 300_000},
    )

    assert transport.invocations[0]["args"] == {"scope": "realm"}
    wire = transport.invocations[1]
    assert wire["callee_ura"] == UUID_AGENT_OWNER_URA
    assert wire["descriptor_ref"] == expected_descriptor_ref(UUID_AGENT_CHAT_URA)
    assert len(transport.descriptor_requests) == 1
    descriptor_request = transport.descriptor_requests[0]
    assert descriptor_request["call"].caller_ura == USER_URA
    assert descriptor_request["call"].callee_ura == INTROSPECTION_URA
    assert descriptor_request["call"].subject_ura == RUNTIME_STATE_SUBJECT
    assert (
        descriptor_request["ability_ura"]
        == UUID_AGENT_CHAT_URA
    )
    assert descriptor_request["call_mode"] == "rpc"
    assert descriptor_request["descriptor_version"] == ""
    assert descriptor_request["scope"] == ""
    assert transport._descriptor_resolver.requests == []
    assert wire["args"] == {
        "messages": messages,
        "execution": {
            "cwd": "benchmarks/run-1/case-1",
            "timeout_ms": 300_000,
            "isolation": "strict",
        },
    }
    assert wire["metadata"] == {
        "easyremote.external_subject": (
            "benchmark://enterprise_knowledge_text2signal/case-1"
        ),
        "easyremote.profile": "agent.chat.strict.v1",
    }
    assert "/benchmark/invocation-subject/" in wire["subject_ura"]
    assert transport.trace_requests[0]["request_id"] == "inv-1"
    assert result.prediction == "MATCH (c:Case) RETURN count(c)"
    assert result.request_id == "inv-1"
    assert result.invocation_ura.endswith("/invocation/inv-1/history")
    assert result.trace_id == "trace-agent-1"
    assert result.status == "completed"
    assert result.elapsed_ms == 1
    assert result.usage == {"input_tokens": 7, "output_tokens": 3}
    assert result.session_id == "unused-strict-session"
    assert result.skills_loaded == ()
    assert result.context_used == ()
    assert result.tool_calls == ()
    assert result.timeline == ()
    assert result.trace == native_agent_trace().to_dict()


def test_bare_agent_id_fails_closed_when_catalogue_has_no_owner():
    client, _ = make_client(responses=[empty_catalogue_response()])

    with pytest.raises(Unavailable) as exc_info:
        client.agent("claude-code").chat(
            messages=[{"role": "user", "content": "hello"}],
            subject="benchmark://suite/case",
            execution={"cwd": "benchmarks/run/case", "timeout_ms": 1_000},
        )

    assert exc_info.value.reason == "agent_owner_unresolved"


def test_agent_chat_preserves_observability_records():
    response = ok_response(
        {
            "session_id": "session-1",
            "reply": "SELECT 1",
            "skills_loaded": ["lotus.sem_filter"],
            "context_used": [{"loader": "benchmark_case", "bytes": 128}],
            "tool_calls": [
                {
                    "ability": "lotus.sem_filter",
                    "args": {"question": "Count all cases."},
                    "result": {"decision": "accept"},
                    "elapsed_ms": 1731,
                    "request_id": "operator-inv-1",
                }
            ],
            "timeline": [
                {
                    "elapsed_ms": 0,
                    "kind": "reasoning",
                    "text": "I need to compare the candidate query.",
                },
                {
                    "elapsed_ms": 1731,
                    "kind": "tool_result",
                    "tool": "lotus.sem_filter",
                    "status": "ok",
                },
            ],
            "usage": {
                "input_tokens": 7,
                "output_tokens": 3,
                "total_cost_usd": 0.01,
            },
            "elapsed_ms": 2000,
        }
    )
    client, _ = make_client(
        responses=[agent_catalogue_response(), response],
        traces=[native_agent_trace()],
    )

    result = client.agent("claude-code").chat(
        messages=[{"role": "user", "content": "Count all cases."}],
        subject="benchmark://suite/case",
        execution={"cwd": "benchmarks/run/case", "timeout_ms": 1_000},
    )

    assert result.session_id == "session-1"
    assert result.skills_loaded == ("lotus.sem_filter",)
    assert result.context_used == ({"loader": "benchmark_case", "bytes": 128},)
    assert result.tool_calls[0]["ability"] == "lotus.sem_filter"
    assert result.tool_calls[0]["elapsed_ms"] == 1731
    assert result.timeline[0]["kind"] == "reasoning"
    assert result.to_dict()["timeline"][1]["tool"] == "lotus.sem_filter"


def test_agent_chat_forwards_driver_model_override():
    response = ok_response(
        {
            "reply": "accept",
            "tool_calls": [],
            "usage": {"input_tokens": 7, "output_tokens": 3},
            "elapsed_ms": 1,
            "session_id": "unused-strict-session",
        }
    )
    client, transport = make_client(
        responses=[agent_catalogue_response(), response],
        traces=[native_agent_trace()],
    )

    client.agent("claude-code").chat(
        messages=[{"role": "user", "content": "Judge this query."}],
        subject="benchmark://enterprise_knowledge_text2signal/case-1",
        execution={"cwd": "benchmarks/run-1/case-1", "timeout_ms": 300_000},
        driver={"model": "gpt-5.5"},
    )

    assert transport.invocations[1]["args"]["driver"] == {"model": "gpt-5.5"}


def test_agent_chat_does_not_mask_success_when_trace_lookup_is_unavailable():
    class TraceUnavailableTransport(FakeTransport):
        def invocation_trace(self, call, *, request_id):
            self.trace_requests.append({"call": call, "request_id": request_id})
            raise InvalidArgument(
                "canonical invocation history read path is unavailable",
                reason="history_read_unavailable",
            )

    transport = TraceUnavailableTransport(
        responses=[
            agent_catalogue_response(),
            ok_response(
                {
                    "reply": "intentdb-easyremote-sdk-ok",
                    "tool_calls": [],
                    "usage": {"output_tokens": 16},
                }
            )
        ]
    )
    client = Client(
        transport=transport,
        identity=IDENTITY,
        invocation_policy=FreshRoot(ResolvedTargetSubject()),
    )

    result = client.agent("claude-code").chat(
        messages=[{"role": "user", "content": "Return exact token."}],
        subject="benchmark://suite/case",
        execution={"cwd": "benchmarks/run/case", "timeout_ms": 1_000},
    )

    assert result.prediction == "intentdb-easyremote-sdk-ok"
    assert result.status == "completed"
    assert result.trace["records"] == []
    assert "trace_lookup_error" in result.trace


@pytest.mark.parametrize(
    "messages",
    [
        [{"role": "assistant", "content": "prior"}],
        [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
        ],
    ],
)
def test_agent_chat_rejects_non_benchmark_conversation_shapes(messages):
    client, transport = make_client()

    with pytest.raises(InvalidArgument):
        client.agent("claude-code").chat(
            messages=messages,
            subject="benchmark://suite/case",
            execution={"cwd": "benchmarks/run/case", "timeout_ms": 1_000},
        )

    assert transport.invocations == []


def test_agent_chat_preserves_runtime_failure_identity():
    class FailingAgentTransport(FakeTransport):
        def invoke(self, draft):
            self.invocations.append(draft.to_json_dict())
            raise InternalError(
                "agent process failed",
                reason="ability_failed",
                invocation_id="inv-failed-1",
            )

    failure_trace = native_agent_trace("inv-failed-1", "failed")
    transport = FailingAgentTransport(
        responses=[agent_catalogue_response()],
        traces=[failure_trace],
    )
    client = Client(
        transport=transport,
        identity=IDENTITY,
        invocation_policy=FreshRoot(ResolvedTargetSubject()),
    )

    with pytest.raises(InternalError) as exc_info:
        client.agent("claude-code").chat(
            messages=[{"role": "user", "content": "Count all cases."}],
            subject="benchmark://suite/case",
            execution={"cwd": "benchmarks/run/case", "timeout_ms": 1_000},
        )

    assert exc_info.value.invocation_id == "inv-failed-1"
    assert exc_info.value.trace == failure_trace.to_dict()
    assert exc_info.value.trace_lookup_error is None
    assert transport.trace_requests[0]["request_id"] == "inv-failed-1"


def test_agent_chat_trace_lookup_failure_does_not_mask_runtime_failure():
    class FailingAgentTransport(FakeTransport):
        def invoke(self, draft):
            self.invocations.append(draft.to_json_dict())
            raise InternalError(
                "agent process failed",
                reason="ability_failed",
                invocation_id="inv-failed-2",
            )

    transport = FailingAgentTransport(responses=[agent_catalogue_response()])
    client = Client(
        transport=transport,
        identity=IDENTITY,
        invocation_policy=FreshRoot(ResolvedTargetSubject()),
    )

    with pytest.raises(InternalError) as exc_info:
        client.agent("claude-code").chat(
            messages=[{"role": "user", "content": "Count all cases."}],
            subject="benchmark://suite/case",
            execution={"cwd": "benchmarks/run/case", "timeout_ms": 1_000},
        )

    assert str(exc_info.value) == "agent process failed"
    assert exc_info.value.invocation_id == "inv-failed-2"
    assert exc_info.value.trace is None
    assert exc_info.value.trace_lookup_error == (
        "AssertionError: no fake invocation trace queued"
    )


def test_agent_chat_rejects_native_trace_without_matching_record():
    client, _ = make_client(
        responses=[
            agent_catalogue_response(),
            ok_response({"reply": "SELECT 1", "tool_calls": [], "usage": {}}),
        ],
        traces=[native_agent_trace("different-request")],
    )

    with pytest.raises(InternalError) as exc_info:
        client.agent("claude-code").chat(
            messages=[{"role": "user", "content": "Count all cases."}],
            subject="benchmark://suite/case",
            execution={"cwd": "benchmarks/run/case", "timeout_ms": 1_000},
        )

    assert exc_info.value.reason == "trace_record_missing"


def test_device_handle_call_matches_node_target():
    client, transport = make_client()
    device = client.device("gpu-2")
    device.call("chat", prompt="hi")

    other, other_tx = make_client()
    other.call(Client.target("chat", node="gpu-2"), prompt="hi")

    assert (
        transport.invocations[0]["descriptor_ref"]
        == other_tx.invocations[0]["descriptor_ref"]
        == expected_descriptor_ref("easynet:///r/acme/ability/system-agent.gpu-2.ability-management.er.chat")
    )
    assert transport.invocations[0]["callee_ura"] == (
        "easynet:///r/acme/agent/device.gpu-2.ability-management"
    )
    assert isinstance(device, RemoteDevice)
    assert not isinstance(device, RemoteOwner)
    assert device.execution_host_ura == "easynet:///r/acme/device/gpu-2"
    assert device.ability_owner_ura == (
        "easynet:///r/acme/agent/device.gpu-2.ability-management"
    )


def test_owner_ability_handle_calls_fully_qualified_native_ability():
    client, transport = make_client(
        responses=[ok_response({"source": "easynet-native"})]
    )

    result = client.device("gpu-2").ability("nativeer.native_echo").call(text="hi")

    assert result == {"source": "easynet-native"}
    wire = transport.invocations[0]
    assert wire["callee_ura"] == (
        "easynet:///r/acme/agent/device.gpu-2.ability-management"
    )
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.gpu-2.ability-management.nativeer.native_echo"
    )
    assert wire["args"] == {"text": "hi"}
    assert transport.carriers == ["unary"]


def test_owner_ability_handle_can_declare_typed_stub():
    client, transport = make_client(responses=[ok_response({"value": 7})])
    native = client.device("gpu-2").ability("nativeer.native_echo")

    @native.remote
    def native_echo(text: str, times: int = 1) -> dict[str, int]: ...

    assert native_echo("hi", times=2) == {"value": 7}
    assert isinstance(native, RemoteAbility)
    assert native.name == "nativeer.native_echo"
    assert native.owner_ura == (
        "easynet:///r/acme/agent/device.gpu-2.ability-management"
    )
    wire = transport.invocations[0]
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.gpu-2.ability-management.nativeer.native_echo"
    )
    assert wire["args"] == {"text": "hi", "times": 2}


def test_owner_ability_handle_streams_fully_qualified_native_ability():
    client, transport = make_client(responses=[{"tick": 1}])

    frames = list(
        client.device("gpu-2").ability("nativeer.native_stream").stream(count=1)
    )

    assert frames == [{"tick": 1}]
    wire = transport.invocations[0]
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.gpu-2.ability-management.nativeer.native_stream"
    )
    assert wire["args"] == {"count": 1}
    assert transport.carriers == ["stream"]


def test_owner_ability_handle_rejects_empty_name():
    client, _ = make_client()

    with pytest.raises(InvalidArgument) as exc_info:
        client.device("gpu-2").ability("  ")

    assert exc_info.value.reason == "invalid_ability_name"


def test_remote_ability_is_exported_from_top_level_package():
    import easyremote

    assert easyremote.RemoteAbility is RemoteAbility


def test_hub_handle_projects_product_policy_onto_realm_authority():
    client, transport = make_client()
    client.hub().call("route", x=1)
    wire = transport.invocations[0]
    assert wire["callee_ura"] == "easynet:///r/acme/authority"
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/authority.er.route"
    )


def test_handle_factories_preserve_owner_and_execution_host_types():
    client, _ = make_client()
    assert isinstance(client.agent("u-alice.chatbot"), RemoteOwner)
    assert isinstance(client.device("gpu-2"), RemoteDevice)
    assert not isinstance(client.device("gpu-2"), RemoteOwner)
    assert isinstance(client.hub(), RemoteOwner)
    assert isinstance(client.missions, MissionControl)


def test_owner_handle_accepts_full_cross_realm_ura():
    client, transport = make_client()
    client.device("easynet:///r/other/device/box1").call("chat", prompt="hi")
    wire = transport.invocations[0]
    # The facade encodes the wire; whether it routes is daemon federation policy.
    assert wire["callee_ura"] == (
        "easynet:///r/other/agent/device.box1.ability-management"
    )


def test_owner_target_rejects_node_and_pick():
    for kwargs in ({"node": "x"}, {"pick": "random"}):
        with pytest.raises(InvalidArgument) as exc_info:
            Client.target("chat", owner_ura="easynet:///r/acme/hub", **kwargs)
        assert exc_info.value.reason == "ambiguous_target_selection"


def test_user_owner_cannot_own_an_ability():
    client, _ = make_client()
    with pytest.raises(InvalidArgument) as exc_info:
        client.call(
            Client.target("chat", owner_ura="easynet:///r/acme/user/u-bob"),
            prompt="hi",
        )
    assert exc_info.value.reason == "invalid_owner_for_ability"


def test_agent_handle_dotted_ability_passes_through():
    client, transport = make_client()
    client.agent("u-alice.chatbot").call("chat.respond", prompt="hi")
    assert transport.invocations[0]["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/u-alice.chatbot.chat.respond"
    )


# -- pick selection ----------------------------------------------------------


def candidate(verb, device_id, schema=None):
    return {
        "ability": verb,
        "qualified_name": f"easynet:///r/acme/ability/system-agent.{device_id}.ability-management.er.{verb}",
        "owner": (
            f"easynet:///r/acme/agent/device.{device_id}.ability-management"
        ),
        "description": "",
        "input_schema": schema or {"type": "object", "properties": {}},
        "visibility": "device",
        "score": 1.0,
        "call_mode": "stream",
    }


def native_candidate(ability_ura, schema=None, descriptor_ref=""):
    return {
        "ability": "native_echo",
        "ability_ura": ability_ura,
        "qualified_name": ability_ura,
        "descriptor_ref": descriptor_ref,
        "owner": "easynet:///r/acme/agent/device.gpu-2.ability-management",
        "description": "Native EasyNet ability.",
        "input_schema": schema
        or {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            PARAMETER_ORDER_KEY: ["text"],
        },
        "visibility": "user",
        "score": 1.0,
        "call_mode": "stream",
    }


def test_functions_user_scope_discovers_native_easynet_ability_for_canonical_ura_call():
    ability_ura = "easynet:///r/acme/ability/system-agent.gpu-2.ability-management.nativeer.native_echo"
    discover = ok_response({"candidates": [native_candidate(ability_ura)]})
    client, transport = make_client(responses=[discover, {"source": "native"}])

    functions = client.functions(query="native_echo", scope="user")
    result = client.call(ability_ura, "hi")

    assert [info.ability_ura for info in functions] == [ability_ura]
    assert result == {"source": "native"}
    discover_wire, call_wire = transport.invocations
    assert discover_wire["args"] == {"scope": "realm"}
    assert call_wire["callee_ura"] == (
        "easynet:///r/acme/agent/device.gpu-2.ability-management"
    )
    assert call_wire["subject_ura"] == ability_ura
    assert call_wire["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.gpu-2.ability-management.nativeer.native_echo"
    )
    assert call_wire["args"] == {"text": "hi"}
    assert transport.carriers == ["runtime", "stream"]


def test_discovered_descriptor_ref_is_used_for_canonical_ura_call():
    ability_ura = "easynet:///r/acme/ability/system-agent.gpu-2.ability-management.nativeer.native_echo"
    descriptor_ref = f"{ability_ura}@1.0.0#{'a' * 64}!stream"
    discover = ok_response(
        {"candidates": [native_candidate(ability_ura, descriptor_ref=descriptor_ref)]}
    )
    client, transport = make_client(responses=[discover, {"source": "native"}])

    client.functions(query="native_echo", scope="user")
    result = client.call(ability_ura, "hi")

    assert result == {"source": "native"}
    assert transport.invocations[1]["descriptor_ref"] == descriptor_ref
    assert transport._descriptor_resolver.requests == [], (
        "discovered descriptor_ref must bypass local diagnostics resolution"
    )


def test_round_robin_alternates_device_candidates():
    discover = ok_response(
        {"candidates": [candidate("fn", "dev-a"), candidate("fn", "dev-b")]}
    )
    client, transport = make_client(responses=[discover])
    client.functions()

    client.execute(Client.target("fn", pick="round_robin"))
    client.execute(Client.target("fn", pick="round_robin"))
    assert transport.carriers[1:] == ["stream", "stream"]
    selected = [w["subject_ura"] for w in transport.invocations[1:]]
    assert selected == [
        "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.fn",
        "easynet:///r/acme/ability/system-agent.dev-b.ability-management.er.fn",
    ]
    assert transport.invocations[1]["callee_ura"] == ABILITY_MANAGER_URA
    assert transport.invocations[1]["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.fn"
    )


def test_pick_random_chooses_a_known_candidate():
    discover = ok_response(
        {"candidates": [candidate("fn", "dev-a"), candidate("fn", "dev-b")]}
    )
    client, transport = make_client(responses=[discover])
    client.functions()
    client.execute(Client.target("fn", pick="random"))
    assert transport.carriers[1] == "stream"
    assert transport.invocations[1]["subject_ura"] in (
        "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.fn",
        "easynet:///r/acme/ability/system-agent.dev-b.ability-management.er.fn",
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

    assert transport.invocations[1]["args"] == {"x": 11}
    assert transport.invocations[2]["args"] == {"y": 22}


def test_discovery_does_not_cache_schema_when_candidate_omits_schema():
    schema = {
        "type": "object",
        "properties": {"x": {"type": "integer"}},
        PARAMETER_ORDER_KEY: ["x"],
    }
    missing_schema = {
        "ability": "fn",
        "qualified_name": "easynet:///r/acme/ability/system-agent.dev-c.ability-management.er.fn",
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
    assert transport.invocations[0]["callee_ura"] == ABILITY_MANAGER_URA


def test_agent_owned_candidates_are_pickable_from_canonical_ura():
    agent_candidate = {
        "ability": "fn",
        "qualified_name": "easynet:///r/acme/ability/user-1.claude.fn",
        "owner": "easynet:///r/acme/agent/user-1.claude",
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
    assert transport.carriers[1] == "unary"
    assert (
        transport.invocations[1]["callee_ura"]
        == "easynet:///r/acme/agent/user-1.claude"
    )
    assert transport.invocations[1]["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/user-1.claude.fn"
    )
    assert transport.invocations[1]["subject_ura"] == agent_candidate["qualified_name"]


def test_invalid_pick_policy_rejected():
    client, _ = make_client()
    with pytest.raises(InvalidArgument) as exc_info:
        client.execute(Client.target("fn", pick="resource_aware"))
    assert exc_info.value.reason == "invalid_pick_policy"


# -- async mirror -------------------------------------------------------------


def test_aio_mirror_executes_same_dispatch():
    import asyncio

    client, transport = make_client()
    result = asyncio.run(client.aio.execute("fn", x=1))
    assert result == {"echo": True}
    assert transport.invocations[0]["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.fn"
    )


def test_aio_mirror_exposes_prepare_stream_and_session():
    import asyncio

    client, transport = make_client()

    prepared = asyncio.run(client.aio.prepare("fn", x=1))
    expected_suffix = f".er.fn@1.0.0#{TEST_DESCRIPTOR_HASH}!{TEST_DESCRIPTOR_ACTION}"
    assert prepared.tuple.descriptor_ref.endswith(expected_suffix)
    assert prepared.tuple.args == {"x": 1}

    stream = asyncio.run(client.aio.stream("fn", x=2))
    assert list(stream) == [{"echo": True}]
    assert transport.invocations[0]["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.fn"
    )

    session = asyncio.run(client.aio.session("fn", x=3))
    assert transport.invocations[1]["descriptor_ref"] == expected_descriptor_ref(
        "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.fn"
    )
    assert transport.streams[0].stream_id == 1
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
    is testable without an SDK transport or a daemon."""

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
    with pytest.raises(DeadlineExceeded, match="no stream frame") as exc_info:
        list(Stream(fs, timeout=0.01))
    assert exc_info.value.reason == "client_wait_timeout"
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
    with pytest.raises(InternalError, match="boom") as exc_info:
        for v in Stream(fs):
            out.append(v)
    assert out == [0, 1], "values before the error are still delivered"
    assert exc_info.value.reason == "function_raised"
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
