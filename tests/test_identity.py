"""URA discipline: everything we emit round-trips the canonical parser."""

from pathlib import Path

import easynet_sdk
import pytest

import easyremote.config as config
from easyremote.errors import InternalError
from easyremote.identity import (
    LocalIdentity,
    device_ability_ura,
    device_ura,
    hub_ura,
)


def test_device_and_hub_shapes_round_trip():
    assert easynet_sdk.parse_ura(device_ura("acme", "dev-a")).kind == "device"
    assert easynet_sdk.parse_ura(hub_ura("acme")).kind == "authority"


def test_ability_ura_comes_from_the_sdk_builder():
    ura = device_ability_ura("acme", "dev-a", "er", "hello")
    parsed = easynet_sdk.parse_ura(ura)
    assert parsed.kind == "ability"
    assert ura == "easynet:///r/acme/ability/device.dev-a.er.hello"


def test_identity_properties_are_validated():
    identity = LocalIdentity(
        realm="acme", node_id="dev-a", username=None, hub_endpoint=""
    )
    assert easynet_sdk.parse_ura(identity.device_ura).kind == "device"


def test_corrupt_credentials_fail_the_round_trip_loudly():
    broken = LocalIdentity(realm="", node_id="dev-a", username=None, hub_endpoint="")
    with pytest.raises(InternalError) as exc_info:
        _ = broken.device_ura
    assert exc_info.value.reason == "ura_round_trip_failed"
    assert "easynet pair" in str(exc_info.value)


def test_local_identity_load_uses_sdk_runtime_projection(monkeypatch):
    environment = easynet_sdk.SdkEnvironment(control_path="/tmp/control.json")
    monkeypatch.setattr(
        config,
        "sdk_environment",
        lambda: environment,
    )
    monkeypatch.setattr(
        environment,
        "runtime_identity_projection",
        lambda: easynet_sdk.RuntimeIdentityProjection(
            realm="acme",
            runtime_instance_id="dev-a",
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
    assert identity.username is None
    assert identity.hub_endpoint == ""
