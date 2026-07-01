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
    "agent_ura",
    "device_ability_ura",
    "device_ura",
    "hub_ura",
    "resource_ura",
]


def device_ura(realm: str, node_id: str) -> str:
    """RFC-001 device shape, validated by the canonical parser."""
    return _validated(f"{axon_ura.URA_SCHEME}{realm}/device/{node_id}")


def agent_ura(realm: str, owner_token: str) -> str:
    """RFC-001 agent owner shape, validated by the canonical parser.

    ``owner_token`` is the ``<user-id>.<agent-id>`` token (the same form the
    Ability URA carries). Axon ships no agent-owner builder yet, so this
    renders the shape and round-trips it through ``parse_ura`` before it
    leaves the module — flag for an Axon ``build_agent_ura`` to replace it.
    """
    return _validated(f"{axon_ura.URA_SCHEME}{realm}/agent/{owner_token}")


def hub_ura(realm: str) -> str:
    """RFC-001 hub singleton shape, validated by the canonical parser."""
    return _validated(f"{axon_ura.URA_SCHEME}{realm}/hub")


def resource_ura(realm: str, owner_id: str, path: str) -> str:
    """Resource URA shape, validated by the canonical parser.

    Axon's Python SDK does not expose a resource builder yet. Keep the
    one local projection here, next to every other identity helper, so
    callers never hand-roll resource URAs inline.
    """
    clean_path = path.strip().strip("/")
    if not clean_path:
        raise InternalError(
            "resource path must not be empty",
            reason="empty_resource_path",
        )
    return _validated(f"{axon_ura.URA_SCHEME}{realm}/resource/{owner_id}/{clean_path}")


def device_ability_ura(
    realm: str, node_id: str, namespace: str, local_name: str
) -> str:
    """Device-owned ability URA — straight from the Axon builder."""
    return _validated(
        axon_ura.build_device_ability_ura(realm, node_id, namespace, local_name)
    )


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
