"""Shared fixtures."""

import shutil
import tempfile
from pathlib import Path

import pytest

from easyremote import _sdk_identity


@pytest.fixture(autouse=True)
def sdk_identity_facade():
    facade = InMemorySdkIdentityFacade()
    _sdk_identity.set_identity_facade_for_tests(facade)
    yield facade
    _sdk_identity.reset_identity_facade_for_tests()


@pytest.fixture()
def short_tmp() -> Path:
    """A short-prefix temp dir for AF_UNIX sockets.

    pytest's tmp_path nests deep enough to blow the ~104-byte
    sun_path limit on macOS; sockets must bind under /tmp instead.
    """
    path = Path(tempfile.mkdtemp(prefix="er-", dir="/tmp"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


class InMemorySdkIdentityFacade:
    """Deterministic test double for the SDK identity facade."""

    def parse_ura(self, value: str) -> _sdk_identity.UraProjection:
        value = value.strip()
        prefix = _sdk_identity.EASYNET_URA_PREFIX + "r/"
        if not value.startswith(prefix):
            raise _invalid_identity(f"invalid URA {value!r}")
        rest = value.removeprefix(prefix)
        realm, separator, tail = rest.partition("/")
        if not realm or not separator:
            raise _invalid_identity(f"invalid URA {value!r}")
        kind, _, body = tail.partition("/")
        if kind == "hub" and not body:
            return _sdk_identity.UraProjection(kind="hub", ura=value, realm=realm)
        if kind == "device" and body:
            return _sdk_identity.UraProjection(kind="device", ura=value, realm=realm)
        if kind == "agent" and body:
            return _sdk_identity.UraProjection(
                kind="agent",
                ura=value,
                realm=realm,
                components={"owner_kind": _agent_owner_kind(body)},
            )
        if kind == "user" and body:
            return _sdk_identity.UraProjection(kind="user", ura=value, realm=realm)
        if kind == "resource" and body:
            return _sdk_identity.UraProjection(kind="resource", ura=value, realm=realm)
        if kind == "ability" and body:
            owner_ura, owner_kind, public_name = self._ability_owner(realm, body)
            namespace, _, local_name = public_name.rpartition(".")
            return _sdk_identity.UraProjection(
                kind="ability",
                ura=value,
                realm=realm,
                components={
                    "owner_ura": owner_ura,
                    "owner_kind": owner_kind,
                    "public_name": public_name,
                    "namespace": namespace,
                    "local_name": local_name or public_name,
                },
            )
        raise _invalid_identity(f"unsupported URA {value!r}")

    def device_ura(self, realm: str, node_id: str) -> str:
        _require_non_empty(realm, "realm")
        _require_non_empty(node_id, "node_id")
        return f"easynet:///r/{realm}/device/{node_id}"

    def agent_ura(self, realm: str, owner_token: str) -> str:
        _require_non_empty(realm, "realm")
        user_id, separator, agent_id = owner_token.strip().partition(".")
        if not user_id or not separator or not agent_id:
            raise _invalid_identity("invalid agent owner token")
        return f"easynet:///r/{realm}/agent/{user_id}.{agent_id}"

    def hub_ura(self, realm: str) -> str:
        _require_non_empty(realm, "realm")
        return f"easynet:///r/{realm}/hub"

    def resource_ura(self, realm: str, owner_id: str, path: str) -> str:
        _require_non_empty(realm, "realm")
        _require_non_empty(owner_id, "owner_id")
        _require_non_empty(path, "path")
        return f"easynet:///r/{realm}/resource/{owner_id}/{path.strip('/')}"

    def device_ability_ura(
        self, realm: str, node_id: str, namespace: str, local_name: str
    ) -> str:
        owner = self.device_ura(realm, node_id)
        return self.owner_ability_ura(owner, f"{namespace}.{local_name}")

    def owner_ability_ura(self, owner_ura: str, ability_name: str) -> str:
        parsed = self.parse_ura(owner_ura)
        ability_name = ability_name.strip()
        if parsed.kind == "device":
            node_id = owner_ura.rsplit("/", 1)[-1]
            return f"easynet:///r/{parsed.realm}/ability/device.{node_id}.{ability_name}"
        if parsed.kind == "hub":
            return f"easynet:///r/{parsed.realm}/ability/hub.{ability_name}"
        if parsed.kind == "agent":
            owner_token = owner_ura.rsplit("/", 1)[-1]
            return f"easynet:///r/{parsed.realm}/ability/{owner_token}.{ability_name}"
        raise _invalid_identity(f"{parsed.kind} owners cannot publish abilities")

    def owner_ura_for_ability(self, ability_ura: str) -> str:
        return self.parse_ura(ability_ura).owner_ura

    def canonical_ability_descriptor_ref(
        self, value: str, descriptor_version: str = ""
    ) -> str:
        value = value.strip()
        if "@" in value:
            ability_ura, version = value.rsplit("@", 1)
            if not version:
                raise _invalid_identity("descriptor version is empty")
            parsed = self.parse_ura(ability_ura)
            if parsed.kind != "ability":
                raise _invalid_identity("descriptor ref must name an Ability URA")
            return f"{ability_ura}@{version}"
        parsed = self.parse_ura(value)
        if parsed.kind != "ability" or not descriptor_version:
            raise _invalid_identity(
                "descriptor ref requires an Ability URA and version"
            )
        return f"{value}@{descriptor_version}"

    def _ability_owner(self, realm: str, body: str) -> tuple[str, str, str]:
        parts = body.split(".")
        if len(parts) < 2:
            raise _invalid_identity(f"invalid Ability URA body {body!r}")
        if parts[0] == "device" and len(parts) >= 3:
            return (
                f"easynet:///r/{realm}/device/{parts[1]}",
                "device",
                ".".join(parts[2:]),
            )
        if parts[0] == "hub" and len(parts) >= 2:
            return f"easynet:///r/{realm}/hub", "hub", ".".join(parts[1:])
        if len(parts) >= 3:
            return (
                f"easynet:///r/{realm}/agent/{parts[0]}.{parts[1]}",
                "agent",
                ".".join(parts[2:]),
            )
        raise _invalid_identity(f"invalid Ability URA body {body!r}")


def _agent_owner_kind(owner_token: str) -> str:
    return "device" if owner_token.startswith("device.") else "user"


def _require_non_empty(value: str, label: str) -> None:
    if not value.strip():
        raise _invalid_identity(f"{label} must not be empty")


def _invalid_identity(message: str) -> _sdk_identity.IdentityFacadeError:
    return _sdk_identity.IdentityFacadeError(message, invalid_argument=True)
