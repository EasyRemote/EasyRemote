"""Local identity: who this process is on the EasyNet.

Source of truth is the pairing-issued ``~/.easynet/credentials.json``
(``EasyNet-Cli/src/persistence/config.rs::Credentials``: ``node_id``,
``realm``, ``hub_endpoint``, optional ``username``).

URA policy (ura-discipline): **Axon owns URA truth.** Ability URAs are
built by ``easynet_axon.ura.build_device_ability_ura``; the device and
hub shapes — which the Python SDK has no builder for yet — are rendered
here and then **round-tripped through ``easynet_axon.ura.parse_ura``**
before they ever leave this module, so nothing this package emits can
disagree with the canonical parser. No other module renders URAs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from easynet_axon import ura as axon_ura

from .config import read_credentials
from .errors import InternalError, Unavailable

__all__ = [
    "LocalIdentity",
    "device_ability_ura",
    "device_route",
    "device_ura",
    "hub_ura",
]


def device_ura(realm: str, node_id: str) -> str:
    """RFC-001 device shape, validated by the canonical parser."""
    return _validated(f"{axon_ura.URA_SCHEME}{realm}/device/{node_id}")


def hub_ura(realm: str) -> str:
    """RFC-001 hub singleton shape, validated by the canonical parser."""
    return _validated(f"{axon_ura.URA_SCHEME}{realm}/hub")


def device_ability_ura(
    realm: str, node_id: str, namespace: str, local_name: str
) -> str:
    """Device-owned ability URA — straight from the Axon builder."""
    return _validated(
        axon_ura.build_device_ability_ura(realm, node_id, namespace, local_name)
    )


def device_route(ability_ura: str) -> tuple[str, str] | None:
    """(callee device URA, wire ability name) for a device-owned ability URA.

    Returns None for agent/hub-owned abilities: their hosting device is
    not derivable from the URA alone, so multi-candidate selection
    cannot address them — a deliberate scope limit, not an oversight.
    """
    try:
        parsed = axon_ura.parse_ura(ability_ura)
    except axon_ura.ParseError:
        return None
    ability = parsed.ability
    if ability is None or not isinstance(ability.owner, axon_ura.DeviceOwner):
        return None
    wire = (
        f"{ability.namespace}.{ability.local_name}"
        if ability.namespace
        else ability.local_name
    )
    return device_ura(parsed.realm, ability.owner.device_id), wire


def _validated(candidate: str) -> str:
    """AXIOM 22.2: every URA must round-trip through the canonical parser."""
    try:
        axon_ura.parse_ura(candidate)
    except axon_ura.ParseError as exc:
        raise InternalError(
            f"constructed URA {candidate!r} is rejected by the canonical parser"
            f" ({exc}) — likely corrupt credentials; re-pair with `easynet pair`",
            reason="ura_round_trip_failed",
        ) from exc
    return candidate


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
