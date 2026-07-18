"""Local identity: who this process is on the EasyNet.

Source of truth is the EasyNet-Cli SDK runtime identity projection. EasyRemote
does not parse daemon credentials directly.

URA policy: **the EasyNet-Cli SDK owns URA truth**. Product helpers below
delegate directly to the SDK and never parse or encode URA grammar.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import easynet_sdk

from .config import runtime_identity_projection
from .errors import InternalError, Unavailable

__all__ = [
    "LocalIdentity",
    "agent_ura",
    "device_ability_ura",
    "device_ura",
    "hub_ura",
    "resource_ura",
]


def device_ura(realm: str, node_id: str) -> str:
    """Build a device URA through the canonical SDK provider."""
    return _validated_build(lambda: easynet_sdk.device_ura(realm, node_id))


def agent_ura(realm: str, owner_token: str) -> str:
    """Build an agent URA through the canonical SDK provider.

    ``owner_token`` is EasyRemote's product input ``<user-id>.<agent-id>``.
    """
    user_id, separator, agent_id = owner_token.strip().partition(".")
    if not user_id or not separator or not agent_id:
        raise _identity_internal_error("agent owner token must be user-id.agent-id")
    return _validated_build(lambda: easynet_sdk.agent_ura(realm, user_id, agent_id))


def hub_ura(realm: str) -> str:
    """Build the realm hub URA through the canonical SDK provider."""
    return _validated_build(lambda: easynet_sdk.hub_ura(realm))


def resource_ura(realm: str, owner_id: str, path: str) -> str:
    """Build a device-owned resource URA through the canonical SDK provider."""
    clean_path = path.strip().strip("/")
    if not clean_path:
        raise InternalError(
            "resource path must not be empty",
            reason="empty_resource_path",
        )
    if not owner_id.startswith("device."):
        raise InternalError(
            f"unsupported resource owner id {owner_id!r}",
            reason="invalid_resource_owner",
        )
    owner = device_ura(realm, owner_id.removeprefix("device."))
    return _validated_build(lambda: easynet_sdk.resource_ura(owner, clean_path))


def device_ability_ura(
    realm: str, node_id: str, namespace: str, local_name: str
) -> str:
    """Build a device-owned Ability URA through the canonical SDK provider."""
    return _validated_build(
        lambda: easynet_sdk.device_ability_ura(
            realm,
            node_id,
            namespace,
            local_name,
        )
    )


def _validated_build(build: Callable[[], str]) -> str:
    try:
        return _validated(build())
    except easynet_sdk.SDKError as exc:
        raise _identity_internal_error(
            f"SDK Addressing provider rejected constructed URA ({exc}) — likely"
            " corrupt credentials; re-pair with `easynet pair`"
        ) from exc


def _validated(candidate: str) -> str:
    """Every emitted URA must round-trip through the SDK provider."""
    try:
        easynet_sdk.parse_ura(candidate)
    except easynet_sdk.SDKError as exc:
        raise _identity_internal_error(
            f"constructed URA {candidate!r} is rejected by the SDK Addressing"
            f" provider ({exc}) — likely corrupt credentials; re-pair with"
            " `easynet pair`",
        ) from exc
    return candidate


def _identity_internal_error(message: str) -> InternalError:
    return InternalError(message, reason="ura_round_trip_failed")


@dataclass(frozen=True)
class LocalIdentity:
    """The paired device this process runs on."""

    realm: str
    node_id: str
    username: str | None
    hub_endpoint: str

    @classmethod
    def load(cls) -> LocalIdentity:
        return cls.from_runtime_projection(runtime_identity_projection())

    @classmethod
    def from_runtime_projection(
        cls,
        projection: Any,
    ) -> LocalIdentity:
        try:
            realm = str(projection.realm)
            node_id = str(projection.device_id)
        except AttributeError as exc:
            raise Unavailable(
                "runtime identity projection is incomplete — re-pair with "
                "`easynet pair`",
                reason="credentials_incomplete",
            ) from exc
        username = getattr(projection, "username", "")
        return cls(
            realm=realm,
            node_id=node_id,
            username=str(username) if username else None,
            hub_endpoint=str(getattr(projection, "hub_endpoint", "")),
        )

    @classmethod
    def from_credentials(cls, credentials: dict[str, Any]) -> LocalIdentity:
        try:
            realm = str(credentials["realm"])
            node_id = str(credentials["node_id"])
        except KeyError as exc:
            raise Unavailable(
                f"credentials.json is missing {exc} — re-pair with `easynet pair`",
                reason="credentials_incomplete",
            ) from None
        username = credentials.get("username")
        return cls(
            realm=realm,
            node_id=node_id,
            username=str(username) if username else None,
            hub_endpoint=str(credentials.get("hub_endpoint", "")),
        )

    @property
    def device_ura(self) -> str:
        return device_ura(self.realm, self.node_id)

    @property
    def hub_ura(self) -> str:
        return hub_ura(self.realm)
