"""Daemon control facade: ability catalogue/install and agent lifecycle."""

import base64
import json

import easynet_sdk
import pytest
from conftest import (
    TEST_DESCRIPTOR_ACTION,
    TEST_DESCRIPTOR_HASH,
    canonical_runtime_receipt_pair,
    expected_descriptor_ref,
)
from easynet_sdk import InvocationLifecycleState as InvocationState

from easyremote.client import Client
from easyremote.control import AbilityControl, AgentControl
from easyremote.errors import InvalidArgument, Unavailable
from easyremote.identity import LocalIdentity

IDENTITY = LocalIdentity(
    realm="acme", node_id="dev-a", username="u-alice", hub_endpoint="hub:443"
)
DEVICE_URA = "easynet:///r/acme/device/dev-a"
USER_URA = "easynet:///r/acme/user/u-alice"
ABILITY_MANAGER_URA = (
    "easynet:///r/acme/agent/device.dev-a.ability-management"
)
AGENT_MANAGER_URA = "easynet:///r/acme/agent/device.dev-a.agent-management"
INTROSPECTION_URA = (
    "easynet:///r/acme/agent/device.dev-a.runtime-introspection"
)
RUNTIME_STATE_SUBJECT = (
    "easynet:///r/acme/resource/user.u-alice/runtime-state/read"
)


def system_ability_ura(owner_ura: str, ability_name: str) -> str:
    return easynet_sdk.owner_ability_ura(owner_ura, ability_name)


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
        del call, scope
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
            descriptor_hash=TEST_DESCRIPTOR_HASH,
            action=TEST_DESCRIPTOR_ACTION,
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
                "ability_ura": "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.fn",
                "state": "ACTIVE",
            }
        )
    )

    result = AbilityControl(client).install(package)

    assert result.install_id == "inst-1"
    wire = transport.invocations[0]
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        system_ability_ura(ABILITY_MANAGER_URA, "ability.deploy")
    )
    assert wire["subject_ura"].startswith("easynet:///r/acme/resource/device.dev-a/fs/")
    assert wire["args"]["node_id"] == "local"
    assert wire["caller_ura"] == USER_URA
    assert wire["callee_ura"] == ABILITY_MANAGER_URA
    assert wire["args"]["target_ura"] == DEVICE_URA
    ref = wire["args"]["resource_ref"]
    assert ref["resource_ura"] == wire["subject_ura"]
    assert ref["owner_ura"] == DEVICE_URA
    assert ref["namespace"] == "fs"
    assert ref["capability"] == "read"
    assert ref["revision"] == "fs-local-mapping-v1"


def test_install_forwards_process_binding_lease(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "ability.json").write_text("{}")
    client, transport = client_with(
        ok_response(
            {
                "install_id": "inst-1",
                "ability_ura": "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.fn",
                "state": "ACTIVE",
            }
        )
    )

    AbilityControl(client).install(package, binding_lease_ms=9_000)

    assert transport.invocations[0]["args"]["binding_lease_ms"] == 9_000


def test_install_resolves_named_node_to_canonical_target_ura(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "ability.json").write_text("{}")
    client, transport = client_with(
        ok_response(
            {
                "install_id": "inst-1",
                "ability_ura": "easynet:///r/acme/ability/system-agent.gpu-2.ability-management.er.fn",
                "state": "ACTIVE",
            }
        )
    )

    result = AbilityControl(client).install(package, node="gpu-2")

    assert result.node_id == "gpu-2"
    wire = transport.invocations[0]
    assert wire["caller_ura"] == USER_URA
    assert wire["callee_ura"] == (
        "easynet:///r/acme/agent/device.gpu-2.ability-management"
    )
    assert wire["args"]["node_id"] == "gpu-2"
    assert wire["args"]["target_ura"] == "easynet:///r/acme/device/gpu-2"


def test_uninstall_revokes_exact_install_binding():
    ability_ura = "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.fn"
    client, transport = client_with(
        ok_response(
            {
                "ability_ura": ability_ura,
                "install_ids": ["inst-1"],
                "state": "REMOVED",
            }
        )
    )

    result = AbilityControl(client).uninstall(ability_ura, install_id="inst-1")

    assert result["state"] == "REMOVED"
    wire = transport.invocations[0]
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        system_ability_ura(ABILITY_MANAGER_URA, "ability.uninstall")
    )
    assert wire["caller_ura"] == USER_URA
    assert wire["callee_ura"] == ABILITY_MANAGER_URA
    assert wire["subject_ura"] == ability_ura
    assert wire["args"] == {
        "ability_ura": ability_ura,
        "install_id": "inst-1",
        "target_ura": DEVICE_URA,
    }


def test_install_rejects_missing_package(tmp_path):
    client, _ = client_with(ok_response({}))
    with pytest.raises(InvalidArgument) as exc_info:
        AbilityControl(client).install(tmp_path / "missing")
    assert exc_info.value.reason == "ability_package_not_directory"


def test_list_abilities_sends_owner_scope_once():
    ability = {
        "name": "er.fn",
        "ability_ura": "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.fn",
        "descriptor_ref": expected_descriptor_ref(
            "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.fn",
            action="stream",
        ),
        "owner_ura": ABILITY_MANAGER_URA,
        "descriptor_version": "1.0.0",
        "description": "demo",
        "state": "ACTIVE",
        "input_schema": {"type": "object"},
    }
    client, transport = client_with(ok_response({"abilities": [ability]}))

    records = AbilityControl(client).list(owner_ura=ABILITY_MANAGER_URA)

    assert records[0].ability_ura == ability["ability_ura"]
    assert records[0].descriptor_ref == ability["descriptor_ref"]
    assert (
        client._addressing.cache.descriptor_ref_for_ura(ability["ability_ura"])
        == ability["descriptor_ref"]
    )
    wire = transport.invocations[0]
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        system_ability_ura(INTROSPECTION_URA, "meta.list_abilities")
    )
    assert wire["caller_ura"] == USER_URA
    assert wire["callee_ura"] == INTROSPECTION_URA
    assert wire["subject_ura"] == RUNTIME_STATE_SUBJECT
    assert wire["args"] == {"owner_ura": ABILITY_MANAGER_URA}


def test_list_abilities_exposes_realm_scope():
    client, transport = client_with(ok_response({"abilities": []}))

    assert AbilityControl(client).list(scope="realm") == []

    assert transport.invocations[0]["args"] == {"scope": "realm"}


def test_show_returns_matching_ability_or_not_found():
    ability_ura = "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.fn"
    client, _ = client_with(
        ok_response(
            {
                "abilities": [
                    {
                        "name": "er.fn",
                        "ability_ura": ability_ura,
                        "owner_ura": ABILITY_MANAGER_URA,
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
            "ability_ura": "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.fn",
            "owner_ura": ABILITY_MANAGER_URA,
            "descriptor_version": "1.0.0",
            "name": "er.fn",
            "metadata": {"owner_user": "u-alice"},
        },
    ]
    client, _ = client_with(ok_response({"abilities": rows}))

    records = AbilityControl(client).list_user("u-alice")

    assert [record.owner_ura for record in records] == [
        "easynet:///r/acme/agent/u-alice.caesura",
        ABILITY_MANAGER_URA,
    ]


def test_remote_node_catalogue_targets_runtime_introspection_system_agent():
    client, transport = client_with(ok_response({"abilities": []}))
    AbilityControl(client).list(node="gpu-2")
    wire = transport.invocations[0]
    assert wire["caller_ura"] == USER_URA
    assert wire["callee_ura"] == (
        "easynet:///r/acme/agent/device.gpu-2.runtime-introspection"
    )
    assert wire["descriptor_ref"] == expected_descriptor_ref(
        system_ability_ura(wire["callee_ura"], "meta.list_abilities")
    )


def test_list_device_with_explicit_owner_targets_that_device_catalogue():
    client, transport = client_with(ok_response({"abilities": []}))

    AbilityControl(client).list_device("gpu-2")

    wire = transport.invocations[0]
    assert wire["callee_ura"] == (
        "easynet:///r/acme/agent/device.gpu-2.runtime-introspection"
    )
    assert wire["args"] == {
        "owner_ura": "easynet:///r/acme/agent/device.gpu-2.ability-management",
    }


def test_list_device_accepts_canonical_device_ura_without_treating_it_as_an_id():
    client, transport = client_with(ok_response({"abilities": []}))

    AbilityControl(client).list_device("easynet:///r/acme/device/gpu-2")

    wire = transport.invocations[0]
    assert wire["callee_ura"] == (
        "easynet:///r/acme/agent/device.gpu-2.runtime-introspection"
    )
    assert wire["args"] == {
        "owner_ura": "easynet:///r/acme/agent/device.gpu-2.ability-management",
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
    assert transport.invocations[0]["descriptor_ref"] == expected_descriptor_ref(
        system_ability_ura(AGENT_MANAGER_URA, "agent.start")
    )
    assert transport.invocations[0]["caller_ura"] == USER_URA
    assert transport.invocations[0]["callee_ura"] == AGENT_MANAGER_URA
    assert transport.invocations[0]["subject_ura"] == DEVICE_URA
    assert transport.invocations[0]["args"]["agent_type"] == "claude-code"
    assert transport.invocations[0]["args"]["materialize_directory"] is True
    assert transport.invocations[1]["descriptor_ref"] == expected_descriptor_ref(
        system_ability_ura(AGENT_MANAGER_URA, "agent.list")
    )
    assert transport.invocations[2]["descriptor_ref"] == expected_descriptor_ref(
        system_ability_ura(AGENT_MANAGER_URA, "agent.stop")
    )
    assert transport.invocations[2]["args"] == {"name": "caesura"}


def test_agent_add_can_request_custom_root_path():
    client, transport = client_with(ok_response({"root_path": "/tmp/run-agent"}))

    control = AgentControl(client)
    result = control.add(
        "codex-exp",
        kind="codex",
        model="gpt-5.5",
        root_path="/tmp/run-agent",
    )

    wire = transport.invocations[0]
    assert wire["args"]["root_path"] == "/tmp/run-agent"
    assert result.root_path == "/tmp/run-agent"


def test_agent_add_preserves_explicit_model_presence_without_a_model():
    client, transport = client_with(ok_response({}))

    AgentControl(client).add("caesura", kind="claude-code")

    assert transport.invocations[0]["args"]["model"] is None
    assert transport.invocations[0]["args"]["model_present"] is True


def test_agent_refresh_accepts_optional_name():
    client, transport = client_with(ok_response({"agents_scanned": 1}))
    assert AgentControl(client).refresh("caesura") == {"agents_scanned": 1}
    assert transport.invocations[0]["args"] == {"name": "caesura"}
