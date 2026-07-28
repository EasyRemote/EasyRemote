"""Daemon control facade: ability catalogue/install and agent lifecycle."""

import base64
import json
import easynet_sdk
import pytest
from conftest import canonical_runtime_receipt_pair
from easynet_sdk import InvocationLifecycleState as InvocationState

from easyremote.client import Client
from easyremote.control import AbilityControl, AgentControl
from easyremote.errors import InvalidArgument, Unavailable
from easyremote.identity import LocalIdentity

IDENTITY = LocalIdentity(
    realm="acme", node_id="dev-a", username="u-alice", hub_endpoint="hub:443"
)
DEVICE_URA = "easynet:///r/acme/device/dev-a"


def ok_response(result):
    payload = json.dumps(result).encode()
    admission, terminal = canonical_runtime_receipt_pair()
    return {
        "ok": True,
        "state": int(InvocationState.COMPLETED),
        "elapsed_ms": 1,
        "result_content_type": "application/json",
        "result_base64": base64.b64encode(payload).decode(),
        "result_json": result,
        "admission_receipt": admission,
        "terminal_receipt": terminal,
    }


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.invocations = []
        self._addressing = easynet_sdk.AddressingClient(
            easynet_sdk.AxonAddressingTransport()
        )
        self._runtime = _FakeRuntime(self)
        self._runtime_client = easynet_sdk.RuntimeClient(self._runtime)
        self._invoker = easynet_sdk.AbilityInvocationClient(
            self._runtime_client,
            self._addressing,
        )
        self._runtime_ability = easynet_sdk.RuntimeAbilityClient(
            self._runtime_client,
            self._addressing,
        )
        self._descriptor_provider = easynet_sdk.RuntimeAbilityDescriptorProvider(
            self._runtime_ability,
        )

    def build_target_invocation(self, request):
        return self._invoker.build_target_invocation(request)

    def invoke(self, draft):
        return self._record_invocation(draft)

    def invoke_runtime_ability(self, call, ability_name, arguments):
        return self._runtime_ability.invoke(call, ability_name, arguments)

    def list_ability_descriptors(
        self,
        call,
        *,
        scope="",
        owner_ura="",
        ability_ura="",
    ):
        page = self._descriptor_provider.list(
            easynet_sdk.AbilityDescriptorListRequest(
                call=call,
                scope=scope,
                owner_ura=owner_ura,
                ability_ura=ability_ura,
            )
        )
        return [
            {
                "name": descriptor.name,
                "ability_ura": descriptor.ability_ura,
                "descriptor_ref": descriptor.descriptor_ref,
                "owner_ura": descriptor.owner_ura,
                "description": descriptor.description,
                "input_schema": dict(descriptor.input_schema),
                "metadata": dict(descriptor.metadata),
            }
            for descriptor in page.descriptors
        ]

    def _record_invocation(self, draft):
        wire = draft.to_json_dict()
        self.invocations.append(wire)
        response = dict(self.responses.pop(0))
        response["sdk_runtime_result"] = {
            "ok": True,
            "tuple": wire,
            "invocation_id": "inv-1",
            "terminal_state": "Completed",
            "output_content_type": response["result_content_type"],
            "output_base64": response["result_base64"],
            "output_json": response["result_json"],
            "elapsed_ms": response["elapsed_ms"],
            "admission_receipt": response["admission_receipt"],
            "terminal_receipt": response["terminal_receipt"],
            "error": None,
        }
        return response

    def close(self):
        self._addressing.close()


class _FakeRuntime:
    def __init__(self, transport: FakeTransport) -> None:
        self._transport = transport

    def resolve_descriptor_ref(self, request_json: bytes) -> bytes:
        request = json.loads(request_json.decode("utf-8"))
        callee = str(request["callee_ura"])
        ability = str(request["ability"])
        if ability.startswith("easynet:///"):
            ability_ura = ability
        else:
            ability_ura = self._transport._addressing.owner_ability_ura(callee, ability)
        descriptor_ref = self._transport._addressing.canonical_ability_descriptor_ref(
            ability_ura,
            "1.0.0",
        )
        return json.dumps({"descriptor_ref": descriptor_ref}).encode()

    def invoke(self, draft_json: bytes) -> bytes:
        draft = easynet_sdk.InvocationDraft.from_json(draft_json.decode("utf-8"))
        response = self._transport._record_invocation(draft)
        return json.dumps(response["sdk_runtime_result"]).encode()


def client_with(*responses):
    transport = FakeTransport(responses)
    return Client(transport=transport, identity=IDENTITY), transport


def test_install_invokes_ability_deploy_with_resource_ref(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "ability.json").write_text("{}")
    client, transport = client_with(
        ok_response(
            {
                "install_id": "inst-1",
                "ability_ura": "easynet:///r/acme/ability/device.dev-a.er.fn",
                "state": "ACTIVE",
            }
        )
    )

    result = AbilityControl(client).install(package)

    assert result.install_id == "inst-1"
    wire = transport.invocations[0]
    assert (
        wire["descriptor_ref"]
        == "easynet:///r/acme/ability/device.dev-a.ability.deploy@1.0.0"
    )
    assert wire["subject_ura"].startswith("easynet:///r/acme/resource/device.dev-a/fs/")
    assert wire["args"]["node_id"] == "local"
    ref = wire["args"]["resource_ref"]
    assert ref["resource_ura"] == wire["subject_ura"]
    assert ref["owner_ura"] == DEVICE_URA
    assert ref["namespace"] == "fs"
    assert ref["capability"] == "read"
    assert ref["revision"] == "fs-local-mapping-v1"


def test_install_rejects_missing_package(tmp_path):
    client, _ = client_with(ok_response({}))
    with pytest.raises(InvalidArgument) as exc_info:
        AbilityControl(client).install(tmp_path / "missing")
    assert exc_info.value.reason == "ability_package_not_directory"


def test_list_abilities_sends_owner_scope_once():
    ability = {
        "name": "er.fn",
        "ability_ura": "easynet:///r/acme/ability/device.dev-a.er.fn",
        "descriptor_ref": "easynet:///r/acme/ability/device.dev-a.er.fn@1.0.0#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa!stream",
        "owner_ura": DEVICE_URA,
        "descriptor_version": "1.0.0",
        "description": "demo",
        "state": "ACTIVE",
        "input_schema": {"type": "object"},
    }
    client, transport = client_with(ok_response({"abilities": [ability]}))

    records = AbilityControl(client).list(owner_ura=DEVICE_URA)

    assert records[0].ability_ura == ability["ability_ura"]
    assert records[0].descriptor_ref == ability["descriptor_ref"]
    assert (
        client._addressing.cache.descriptor_ref_for_ura(ability["ability_ura"])
        == ability["descriptor_ref"]
    )
    wire = transport.invocations[0]
    assert (
        wire["descriptor_ref"]
        == "easynet:///r/acme/ability/device.dev-a.meta.list_abilities@1.0.0"
    )
    assert wire["args"] == {"owner_ura": DEVICE_URA}


def test_list_abilities_exposes_realm_scope():
    client, transport = client_with(ok_response({"abilities": []}))

    assert AbilityControl(client).list(scope="realm") == []

    assert transport.invocations[0]["args"] == {"scope": "realm"}


def test_show_returns_matching_ability_or_not_found():
    ability_ura = "easynet:///r/acme/ability/device.dev-a.er.fn"
    client, _ = client_with(
        ok_response(
            {
                "abilities": [
                    {
                        "name": "er.fn",
                        "ability_ura": ability_ura,
                        "owner_ura": DEVICE_URA,
                        "descriptor_version": "1.0.0",
                    }
                ]
            }
        )
    )
    assert AbilityControl(client).show(ability_ura).ability_ura == ability_ura

    missing, _ = client_with(ok_response({"abilities": []}))
    with pytest.raises(Unavailable) as exc_info:
        AbilityControl(missing).show(ability_ura)
    assert exc_info.value.reason == "ability_not_found"


def test_list_user_filters_agent_and_user_owned_rows():
    rows = [
        {
            "ability_ura": "easynet:///r/acme/ability/u-alice.caesura.chat",
            "owner_ura": "easynet:///r/acme/agent/u-alice.caesura",
            "descriptor_version": "1.0.0",
            "name": "caesura.chat",
        },
        {
            "ability_ura": "easynet:///r/acme/ability/u-bob.caesura.chat",
            "owner_ura": "easynet:///r/acme/agent/u-bob.caesura",
            "descriptor_version": "1.0.0",
            "name": "caesura.chat",
        },
        {
            "ability_ura": "easynet:///r/acme/ability/device.dev-a.er.fn",
            "owner_ura": DEVICE_URA,
            "descriptor_version": "1.0.0",
            "name": "er.fn",
            "metadata": {"owner_user": "u-alice"},
        },
    ]
    client, _ = client_with(ok_response({"abilities": rows}))

    records = AbilityControl(client).list_user("u-alice")

    assert [record.owner_ura for record in records] == [
        "easynet:///r/acme/agent/u-alice.caesura",
        DEVICE_URA,
    ]


def test_remote_node_catalogue_targets_that_device_owner():
    client, transport = client_with(ok_response({"abilities": []}))
    AbilityControl(client).list(node="gpu-2")
    wire = transport.invocations[0]
    assert wire["callee_ura"] == "easynet:///r/acme/device/gpu-2"
    assert (
        wire["descriptor_ref"]
        == "easynet:///r/acme/ability/device.gpu-2.meta.list_abilities@1.0.0"
    )


def test_list_device_with_explicit_owner_targets_that_device_catalogue():
    client, transport = client_with(ok_response({"abilities": []}))

    AbilityControl(client).list_device("gpu-2")

    wire = transport.invocations[0]
    assert wire["callee_ura"] == "easynet:///r/acme/device/gpu-2"
    assert wire["args"] == {
        "owner_ura": "easynet:///r/acme/device/gpu-2",
    }


def test_agent_add_and_list_use_daemon_system_abilities():
    client, transport = client_with(
        ok_response({"root_path": "/tmp/agent", "model": "sonnet"}),
        ok_response(
            {
                "agents": [
                    {
                        "name": "caesura",
                        "runtime": "claude-code",
                        "model": "sonnet",
                        "metadata": {
                            "root_path": "/tmp/caesura",
                            "timeout_secs": 30,
                            "root_exists": True,
                        },
                    }
                ]
            }
        ),
        ok_response(
            {
                "ack": True,
                "agent_ura": "easynet:///r/acme/agent/caesura",
            }
        ),
    )
    control = AgentControl(client)

    added = control.add("caesura", kind="claude-code", model="sonnet")
    listed = control.list()
    stopped = control.stop("caesura")

    assert added.name == "caesura"
    assert listed[0].runtime == "claude-code"
    assert listed[0].root_path == "/tmp/caesura"
    assert listed[0].timeout_secs == 30
    assert listed[0].root_exists is True
    assert stopped.name == "caesura"
    assert stopped.stopped is True
    assert stopped.agent_ura == "easynet:///r/acme/agent/caesura"
    assert transport.invocations[0]["descriptor_ref"].endswith(
        "/ability/device.dev-a.agent.start@1.0.0"
    )
    assert transport.invocations[0]["args"]["agent_type"] == "claude-code"
    assert transport.invocations[0]["args"]["materialize_directory"] is True
    assert transport.invocations[1]["descriptor_ref"].endswith(
        "/ability/device.dev-a.agent.list@1.0.0"
    )
    assert transport.invocations[2]["descriptor_ref"].endswith(
        "/ability/device.dev-a.agent.stop@1.0.0"
    )
    assert transport.invocations[2]["args"] == {"name": "caesura"}


def test_agent_add_preserves_explicit_model_presence_without_a_model():
    client, transport = client_with(ok_response({}))

    AgentControl(client).add("caesura", kind="claude-code")

    assert transport.invocations[0]["args"]["model"] is None
    assert transport.invocations[0]["args"]["model_present"] is True


def test_agent_refresh_accepts_optional_name():
    client, transport = client_with(ok_response({"agents_scanned": 1}))
    assert AgentControl(client).refresh("caesura") == {"agents_scanned": 1}
    assert transport.invocations[0]["args"] == {"name": "caesura"}
