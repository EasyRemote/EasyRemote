"""URA discipline: everything we emit round-trips the canonical parser."""

import pytest
from easynet_axon.ura import parse_ura

from easyremote.errors import InternalError
from easyremote.identity import (
    LocalIdentity,
    device_ability_ura,
    device_ura,
    hub_ura,
)


def test_device_and_hub_shapes_round_trip():
    assert parse_ura(device_ura("acme", "dev-a")).kind == "device"
    assert parse_ura(hub_ura("acme")).kind == "hub"


def test_ability_ura_comes_from_the_axon_builder():
    ura = device_ability_ura("acme", "dev-a", "er", "hello")
    parsed = parse_ura(ura)
    assert parsed.kind == "ability"
    assert ura == "easynet:///r/acme/ability/device.dev-a.er.hello"


def test_identity_properties_are_validated():
    identity = LocalIdentity(
        realm="acme", node_id="dev-a", username=None, hub_endpoint=""
    )
    assert parse_ura(identity.device_ura).kind == "device"


def test_corrupt_credentials_fail_the_round_trip_loudly():
    broken = LocalIdentity(realm="", node_id="dev-a", username=None, hub_endpoint="")
    with pytest.raises(InternalError) as exc_info:
        _ = broken.device_ura
    assert exc_info.value.reason == "ura_round_trip_failed"
    assert "easynet pair" in str(exc_info.value)
