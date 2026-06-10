"""Local identity: who this process is on the EasyNet.

Source of truth is the pairing-issued ``~/.easynet/credentials.json``
(``EasyNet-Cli/src/persistence/config.rs::Credentials``: ``node_id``,
``realm``, ``hub_endpoint``, optional ``username``).

URA construction policy (ura-discipline): this module is the ONLY
place in the package that renders URA strings, and it renders exactly
the two RFC-001 §URA canonical shapes mirrored in
``EasyNet-Cli/src/ura.rs:14-28``:

    device  easynet:///r/<realm>/device/<device-id>
    hub     easynet:///r/<realm>/hub          (singleton, no tail)

Every other URA (abilities, agents, receipts) reaches this package
pre-built — from daemon `discover` responses or Axon builders — and
is passed through verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import read_credentials
from .errors import Unavailable

__all__ = ["LocalIdentity"]

_URA_SCHEME = "easynet:///r"


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
        """This device's URA (RFC-001 §URA device shape)."""
        return f"{_URA_SCHEME}/{self.realm}/device/{self.node_id}"

    @property
    def hub_ura(self) -> str:
        """The realm hub's URA (RFC-001 §URA hub singleton shape)."""
        return f"{_URA_SCHEME}/{self.realm}/hub"
