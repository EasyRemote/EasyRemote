"""Daemon control-plane facades for abilities and agents.

This module is the Python boundary for EasyNet daemon system abilities.
It does not define new protocol semantics: every operation below builds
ordinary EasyRemote invocations through :class:`easyremote.client.Client`.

The important separation is:

- lifecycle (`DaemonHandle`) starts/stops a daemon process;
- invocation (`Client`) sends complete Axon seven-tuples;
- control (`AbilityControl` / `AgentControl`) maps product operations
  such as install/list/add into daemon-owned system abilities.
"""

from __future__ import annotations

import builtins
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import easynet_sdk

from . import _sdk_identity
from .errors import InternalError, InvalidArgument, RemoteError, Unavailable
from .identity import LocalIdentity

if TYPE_CHECKING:
    from .client import Client

__all__ = [
    "AbilityControl",
    "AbilityInstallResult",
    "AbilityRecord",
    "AgentControl",
    "AgentRecord",
    "AgentStartResult",
]

AbilityListScope = Literal["local", "realm"]


@dataclass(frozen=True)
class AbilityRecord:
    """One row from the daemon `meta.list_abilities` catalogue."""

    name: str
    ability_ura: str
    owner_ura: str
    description: str = ""
    state: str = ""
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> AbilityRecord:
        return cls(
            name=str(value.get("name") or value.get("ability") or ""),
            ability_ura=str(
                value.get("ability_ura")
                or value.get("qualified_name")
                or value.get("descriptor_ref")
                or ""
            ),
            owner_ura=str(value.get("owner_ura") or ""),
            description=str(value.get("description") or ""),
            state=str(value.get("state") or ""),
            input_schema=_optional_dict(value.get("input_schema")),
            metadata=_optional_dict(value.get("metadata")),
            raw=dict(value),
        )


@dataclass(frozen=True)
class AbilityInstallResult:
    """Daemon response from `ability.deploy`."""

    install_id: str
    ability_ura: str
    state: str
    node_id: str
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_wire(
        cls, value: Mapping[str, Any], *, node_id: str
    ) -> AbilityInstallResult:
        return cls(
            install_id=str(value.get("install_id") or ""),
            ability_ura=str(value.get("ability_ura") or ""),
            state=str(value.get("state") or ""),
            node_id=node_id,
            raw=dict(value),
        )


@dataclass(frozen=True)
class AgentRecord:
    """One daemon-owned registered agent."""

    name: str
    runtime: str
    model: str | None = None
    root_path: str | None = None
    timeout_secs: int | None = None
    root_exists: bool | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> AgentRecord:
        return cls(
            name=str(value.get("name") or ""),
            runtime=str(value.get("runtime") or value.get("agent_type") or ""),
            model=_optional_str(value.get("model")),
            root_path=_optional_str(value.get("root_path")),
            timeout_secs=_optional_int(value.get("timeout_secs")),
            root_exists=_optional_bool(value.get("root_exists")),
            raw=dict(value),
        )


@dataclass(frozen=True)
class AgentStartResult:
    """Daemon response from `agent.start`."""

    name: str
    runtime: str
    model: str | None
    root_path: str | None
    replaced_prior: bool
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_wire(
        cls, value: Mapping[str, Any], *, name: str, runtime: str
    ) -> AgentStartResult:
        return cls(
            name=name,
            runtime=runtime,
            model=_optional_str(value.get("model")),
            root_path=_optional_str(value.get("root_path")),
            replaced_prior=bool(value.get("replaced_prior", False)),
            raw=dict(value),
        )


class AbilityControl:
    """Ability install/catalogue facade over daemon system abilities.

    What this is not: a registry implementation. It submits complete
    invocations to the daemon, which remains the authority for install
    validation, registry mutation, federation routing, and receipts.
    """

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or _new_client()
        self._publication = easynet_sdk.EasyRemotePublicationAdapter(
            self._client,
            addressing=_sdk_identity.identity_facade(),
        )

    def install(self, path: str | Path, *, node: str = "local") -> AbilityInstallResult:
        """Install an ability package by invoking daemon `ability.deploy`."""
        node_id = node.strip()
        if not node_id:
            raise InvalidArgument("install node must not be empty", reason="empty_node")
        package = Path(path)
        if not package.is_dir():
            raise InvalidArgument(
                f"ability package path is not a directory: {package}",
                reason="ability_package_not_directory",
            )

        try:
            result = self._publication.install_ability(package, node_id=node_id)
        except easynet_sdk.SDKError as exc:
            raise _easyremote_publication_error(exc) from exc
        return AbilityInstallResult(
            install_id=result.install_id,
            ability_ura=result.ability_ura,
            state=result.state,
            node_id=result.node_id,
            raw=result.raw,
        )

    def list(
        self,
        *,
        node: str | None = None,
        owner_ura: str | None = None,
        user_id: str | None = None,
        subject_ura: str | None = None,
        scope: AbilityListScope = "local",
    ) -> builtins.list[AbilityRecord]:
        """List abilities from one daemon catalogue.

        `node` selects which daemon to ask; `scope` selects the
        daemon's local catalogue or the realm-wide hub-published view.

        `owner_ura` is encoded into the daemon's historical
        `agent_ura` request field. The field name is historical; the
        value is any canonical ability owner URA accepted by the daemon.
        """
        if scope not in ("local", "realm"):
            raise InvalidArgument(
                f"unsupported ability list scope {scope!r}",
                reason="invalid_ability_scope",
            )
        user = user_id.strip() if user_id is not None else None
        if user_id is not None and not user:
            raise InvalidArgument("user_id must not be empty", reason="empty_user_id")

        try:
            records = [
                AbilityRecord(
                    name=row.name,
                    ability_ura=row.ability_ura,
                    owner_ura=row.owner_ura,
                    description=row.description,
                    state=row.state,
                    input_schema=row.input_schema,
                    metadata=row.metadata,
                    raw=row.raw,
                )
                for row in self._publication.list_abilities(
                    node=node,
                    owner_ura=owner_ura or "",
                    subject_ura=subject_ura or "",
                    scope=scope,
                )
            ]
        except easynet_sdk.SDKError as exc:
            raise _easyremote_publication_error(exc) from exc
        if user is None:
            return records
        return [record for record in records if _record_belongs_to_user(record, user)]

    def list_device(self, device: str | None = None) -> builtins.list[AbilityRecord]:
        """List abilities owned by this device, or another device owner."""
        owner = (
            self._identity().device_ura
            if device is None
            else self._device_owner(device)
        )
        return self.list(owner_ura=owner)

    def list_user(
        self,
        user_id: str | None = None,
        *,
        scope: AbilityListScope = "realm",
    ) -> builtins.list[AbilityRecord]:
        """List abilities owned by this paired user across catalogue rows."""
        user = user_id or self._identity().username
        if not user:
            raise InvalidArgument(
                "user_id is required because credentials have no username",
                reason="missing_user_id",
            )
        return self.list(user_id=user, scope=scope)

    def show(
        self,
        ability_ura: str,
        *,
        node: str | None = None,
        scope: AbilityListScope = "local",
    ) -> AbilityRecord:
        """Return one ability catalogue row by canonical Ability URA."""
        target = ability_ura.strip()
        if not target:
            raise InvalidArgument(
                "ability_ura must not be empty", reason="empty_ability_ura"
            )
        matches = self.list(node=node, subject_ura=target, scope=scope)
        for record in matches:
            if record.ability_ura == target:
                return record
        raise Unavailable(
            f"ability {target!r} was not found in the daemon catalogue",
            reason="ability_not_found",
        )

    def _device_owner(self, node: str) -> str:
        return self._publication.device_owner_ura(node)

    def _identity(self) -> LocalIdentity:
        return self._client._who()


class AgentControl:
    """Daemon-owned agent lifecycle facade."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or _new_client()
        self._admin = easynet_sdk.EasyRemoteAdminAdapter(self._client)

    def add(
        self,
        name: str,
        *,
        kind: str,
        model: str | None = None,
        label: str | None = None,
        command: str | None = None,
        args: Sequence[str] = (),
    ) -> AgentStartResult:
        agent_name = name.strip()
        runtime = kind.strip()
        if not agent_name:
            raise InvalidArgument(
                "agent name must not be empty", reason="empty_agent_name"
            )
        if not runtime:
            raise InvalidArgument(
                "agent type must not be empty", reason="empty_agent_type"
            )

        try:
            result = self._admin.start_agent(
                agent_name,
                kind=runtime,
                model=model,
                label=label,
                command=command,
                args=args,
            )
        except easynet_sdk.SDKError as exc:
            raise _easyremote_admin_error(exc) from exc
        return AgentStartResult(
            name=result.name,
            runtime=result.runtime,
            model=result.model,
            root_path=result.root_path,
            replaced_prior=result.replaced_prior,
            raw=result.raw,
        )

    def list(self) -> builtins.list[AgentRecord]:
        try:
            return [
                AgentRecord(
                    name=row.name,
                    runtime=row.runtime,
                    model=row.model,
                    root_path=row.root_path,
                    timeout_secs=row.timeout_secs,
                    root_exists=row.root_exists,
                    raw=row.raw,
                )
                for row in self._admin.list_agents()
            ]
        except easynet_sdk.SDKError as exc:
            raise _easyremote_admin_error(exc) from exc

    def refresh(self, name: str | None = None) -> Mapping[str, Any]:
        try:
            return dict(self._admin.refresh_agents(name))
        except easynet_sdk.SDKError as exc:
            raise _easyremote_admin_error(exc) from exc


def _easyremote_admin_error(error: easynet_sdk.SDKError) -> RemoteError:
    if isinstance(error.cause, RemoteError):
        return error.cause
    message = error.message or str(error)
    if error.code == easynet_sdk.ErrorCode.INVALID_ARGUMENT:
        return InvalidArgument(message, reason="sdk_admin_invalid_argument")
    if error.code in {
        easynet_sdk.ErrorCode.ABILITY_NOT_FOUND,
        easynet_sdk.ErrorCode.NOT_FOUND,
        easynet_sdk.ErrorCode.DAEMON_OFFLINE,
        easynet_sdk.ErrorCode.ROUTE_UNAVAILABLE,
    }:
        return Unavailable(message, reason="sdk_admin_unavailable")
    if error.retryable:
        return Unavailable(message, reason="sdk_admin_retryable")
    return InternalError(message, reason="sdk_admin_internal")


def _record_belongs_to_user(record: AbilityRecord, user_id: str) -> bool:
    if any(
        str(record.metadata.get(key) or "") == user_id
        for key in (
            "owner_user",
            "owner_user_id",
            "user_id",
            "local_user_id",
        )
    ):
        return True
    try:
        parsed = _sdk_identity.parse_ura(record.owner_ura)
    except _sdk_identity.IdentityFacadeError:
        return False
    if str(parsed.kind) == "user":
        return record.owner_ura.rstrip("/").endswith(f"/user/{user_id}")
    if str(parsed.kind) != "agent":
        return False
    marker = "/agent/"
    _, _, tail = record.owner_ura.partition(marker)
    return tail.split(".", 1)[0] == user_id


def _easyremote_publication_error(error: easynet_sdk.SDKError) -> RemoteError:
    if isinstance(error.cause, RemoteError):
        return error.cause
    message = error.message or str(error)
    if error.code == easynet_sdk.ErrorCode.INVALID_ARGUMENT:
        return InvalidArgument(message, reason="sdk_publication_invalid_argument")
    if error.code in {
        easynet_sdk.ErrorCode.ABILITY_NOT_FOUND,
        easynet_sdk.ErrorCode.NOT_FOUND,
        easynet_sdk.ErrorCode.DAEMON_OFFLINE,
        easynet_sdk.ErrorCode.ROUTE_UNAVAILABLE,
    }:
        return Unavailable(message, reason="sdk_publication_unavailable")
    if error.retryable:
        return Unavailable(message, reason="sdk_publication_retryable")
    return InternalError(message, reason="sdk_publication_internal")


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    raise InvalidArgument(
        f"expected a JSON object, got {type(value).__name__}",
        reason="invalid_daemon_response",
    )


def _optional_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    return _dict(value)


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_bool(value: Any) -> bool | None:
    return bool(value) if value is not None else None


def _new_client() -> Client:
    from .client import Client

    return Client()
