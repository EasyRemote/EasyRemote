"""Daemon control facade: ability catalogue/install and agent lifecycle."""

import base64
import json
from typing import cast

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
        self._invoker = easynet_sdk.AbilityInvocationClient(
            cast(easynet_sdk.RuntimeClient, object()),
            self._addressing,
        )

    def build_target_invocation(self, request):
        return self._invoker.build_target_invocation(request)

    def invoke(self, draft):
        wire = draft.to_json_dict()
        self.invocations.append(wire)
        response = dict(self.responses.pop(0))
        response["sdk_runtime_result"] = {
            "ok": True,
            "tuple": wire,
            "invocation_id": "inv-1",
            "terminal_state": "completed",
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
        "owner_ura": DEVICE_URA,
        "description": "demo",
        "state": "ACTIVE",
        "input_schema": {"type": "object"},
    }
    client, transport = client_with(ok_response({"abilities": [ability]}))

    records = AbilityControl(client).list(owner_ura=DEVICE_URA)

    assert records[0].ability_ura == ability["ability_ura"]
    wire = transport.invocations[0]
    assert (
        wire["descriptor_ref"]
        == "easynet:///r/acme/ability/device.dev-a.meta.list_abilities@1.0.0"
    )
    assert wire["args"] == {"agent_ura": DEVICE_URA}


def test_list_abilities_exposes_realm_scope():
    client, transport = client_with(ok_response({"abilities": []}))

    assert AbilityControl(client).list(scope="realm") == []

    assert transport.invocations[0]["args"] == {"scope": "realm"}


def test_show_returns_matching_ability_or_not_found():
    ability_ura = "easynet:///r/acme/ability/device.dev-a.er.fn"
    client, _ = client_with(ok_response({"abilities": [{"ability_ura": ability_ura}]}))
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
        },
        {
            "ability_ura": "easynet:///r/acme/ability/u-bob.caesura.chat",
            "owner_ura": "easynet:///r/acme/agent/u-bob.caesura",
        },
        {
            "ability_ura": "easynet:///r/acme/ability/device.dev-a.er.fn",
            "owner_ura": DEVICE_URA,
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
