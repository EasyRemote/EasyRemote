"""Local identity: who this process is on the EasyNet.

Source of truth is the pairing-issued ``~/.easynet/credentials.json``
(``EasyNet-Cli/src/persistence/config.rs::Credentials``: ``node_id``,
``realm``, ``hub_endpoint``, optional ``username``).

URA policy (ura-discipline): **the EasyNet-Cli SDK owns URA truth**.
All builders below delegate through ``easyremote._sdk_identity`` so
EasyRemote does not carry Axon parser or builder imports in product code.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from . import _sdk_identity
from .config import read_credentials
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
    """RFC-001 device shape, built by the SDK identity facade."""
    return _validated_build(lambda: _sdk_identity.device_ura(realm, node_id))


def agent_ura(realm: str, owner_token: str) -> str:
    """RFC-001 agent owner shape, built by the SDK identity facade.

    ``owner_token`` is the ``<user-id>.<agent-id>`` token (the same form the
    Ability URA carries).
    """
    return _validated_build(lambda: _sdk_identity.agent_ura(realm, owner_token))


def hub_ura(realm: str) -> str:
    """RFC-001 hub singleton shape, built by the SDK identity facade."""
    return _validated_build(lambda: _sdk_identity.hub_ura(realm))


def resource_ura(realm: str, owner_id: str, path: str) -> str:
    """Resource URA shape, built by the SDK identity facade."""
    clean_path = path.strip().strip("/")
    if not clean_path:
        raise InternalError(
            "resource path must not be empty",
            reason="empty_resource_path",
        )
    return _validated_build(
        lambda: _sdk_identity.resource_ura(realm, owner_id, clean_path)
    )


def device_ability_ura(
    realm: str, node_id: str, namespace: str, local_name: str
) -> str:
    """Device-owned ability URA, built by the SDK identity facade."""
    return _validated_build(
        lambda: _sdk_identity.device_ability_ura(
            realm,
            node_id,
            namespace,
            local_name,
        )
    )


def _validated_build(build: Callable[[], str]) -> str:
    try:
        return _validated(build())
    except _sdk_identity.IdentityFacadeError as exc:
        raise _identity_internal_error(
            f"SDK identity facade rejected constructed URA ({exc}) — likely"
            " corrupt credentials; re-pair with `easynet pair`"
        ) from exc


def _validated(candidate: str) -> str:
    """AXIOM 22.2: every URA must round-trip through the SDK facade."""
    try:
        _sdk_identity.parse_ura(candidate)
    except _sdk_identity.IdentityFacadeError as exc:
        raise _identity_internal_error(
            f"constructed URA {candidate!r} is rejected by the SDK identity"
            f" facade ({exc}) — likely corrupt credentials; re-pair with"
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
        return cls.from_credentials(read_credentials())

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
