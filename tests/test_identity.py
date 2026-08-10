"""URA discipline: everything we emit round-trips the canonical parser."""

from pathlib import Path

import easynet_sdk
import pytest

import easyremote.config as config
from easyremote.errors import InternalError, Unavailable
from easyremote.identity import (
    LocalIdentity,
    device_ura,
    hub_ura,
    system_agent_ability_ura,
    system_agent_ura,
    user_ura,
)


def test_device_and_hub_shapes_round_trip():
    assert easynet_sdk.parse_ura(device_ura("acme", "dev-a")).kind == "device"
    assert easynet_sdk.parse_ura(hub_ura("acme")).kind == "authority"


def test_ability_ura_comes_from_the_sdk_builder():
    owner = system_agent_ura("acme", "dev-a", "ability-management")
    ura = system_agent_ability_ura(
        "acme", "dev-a", "ability-management", "er.hello"
    )
    parsed = easynet_sdk.parse_ura(ura)
    assert parsed.kind == "ability"
    assert ura == easynet_sdk.owner_ability_ura(owner, "er.hello")


def test_user_and_system_agent_roles_are_distinct():
    assert user_ura("acme", "u-alice") == "easynet:///r/acme/user/u-alice"
    assert system_agent_ura(
        "acme", "dev-a", "ability-management"
    ) == "easynet:///r/acme/agent/device.dev-a.ability-management"


def test_identity_properties_are_validated():
    identity = LocalIdentity(
        realm="acme", node_id="dev-a", username=None, hub_endpoint=""
    )
    assert easynet_sdk.parse_ura(identity.device_ura).kind == "device"


def test_identity_projects_paired_user_and_fails_closed_without_one():
    paired = LocalIdentity(
        realm="acme", node_id="dev-a", username="u-alice", hub_endpoint=""
    )
    assert paired.user_ura == "easynet:///r/acme/user/u-alice"

    unpaired = LocalIdentity(
        realm="acme", node_id="dev-a", username=None, hub_endpoint=""
    )
    with pytest.raises(Unavailable) as exc_info:
        _ = unpaired.user_ura
    assert exc_info.value.reason == "paired_user_required"


def test_corrupt_credentials_fail_the_round_trip_loudly():
    broken = LocalIdentity(realm="", node_id="dev-a", username=None, hub_endpoint="")
    with pytest.raises(InternalError) as exc_info:
        _ = broken.device_ura
    assert exc_info.value.reason == "ura_round_trip_failed"
    assert "easynet pair" in str(exc_info.value)


def test_local_identity_load_uses_sdk_runtime_projection(monkeypatch):
    environment = easynet_sdk.SdkEnvironment(control_path="/tmp/control.json")
    requested_paths: list[str | Path] = []
    monkeypatch.setattr(
        config,
        "sdk_environment",
        lambda: environment,
    )
    monkeypatch.setattr(
        environment,
        "runtime_identity_projection",
        lambda credentials_path="": (
            requested_paths.append(credentials_path)
            or easynet_sdk.RuntimeIdentityProjection(
                realm="acme",
                runtime_instance_id="dev-a",
                principal="easynet:///r/acme/user/u-alice",
            )
        ),
    )
    monkeypatch.setattr(
        config,
        "settings",
        lambda: config.Settings(
            credentials_path=Path("/tmp/credentials.json"),
            control_path=Path("/tmp/control.json"),
            library_path=None,
        ),
    )

    identity = LocalIdentity.load()

    assert identity.realm == "acme"
    assert identity.node_id == "dev-a"
    assert identity.username == "easynet:///r/acme/user/u-alice"
    assert identity.user_ura == "easynet:///r/acme/user/u-alice"
    assert identity.hub_endpoint == ""
    assert requested_paths == [Path("/tmp/credentials.json")]
