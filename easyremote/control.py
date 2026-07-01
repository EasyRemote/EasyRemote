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
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from easynet_axon import ura as axon_ura

from .errors import InvalidArgument, Unavailable
from .identity import LocalIdentity, resource_ura

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

_RESOURCE_NAMESPACE_FS = "fs"
_RESOURCE_REF_REVISION = "fs-local-mapping-v1"
_RESOURCE_REF_TTL_MS = 5 * 60 * 1000
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

        ref = LocalFilesystemResourceRefFactory(self._identity()).for_path(
            package,
            capability="read",
        )
        response = self._client.invoke(
            self._client.target("ability.deploy", subject=ref["resource_ura"]),
            resource_ref=ref,
            node_id=node_id,
        ).result()
        return AbilityInstallResult.from_wire(_dict(response), node_id=node_id)

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
        if owner_ura is not None:
            owner_ura = _validated_owner_ura(owner_ura)
        if subject_ura is not None:
            subject_ura = _validated_non_empty_ura(subject_ura, "subject_ura")
        user = user_id.strip() if user_id is not None else None
        if user_id is not None and not user:
            raise InvalidArgument("user_id must not be empty", reason="empty_user_id")

        request: dict[str, Any] = {}
        if scope == "realm":
            request["scope"] = scope
        if owner_ura is not None:
            request["agent_ura"] = owner_ura
        if subject_ura is not None:
            request["subject_ura"] = subject_ura

        records = [
            AbilityRecord.from_wire(row)
            for row in _list_payload(self._invoke_catalogue(node=node, request=request))
        ]
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
        target = _validated_ability_ura(ability_ura)
        matches = self.list(node=node, subject_ura=target, scope=scope)
        for record in matches:
            if record.ability_ura == target:
                return record
        raise Unavailable(
            f"ability {target!r} was not found in the daemon catalogue",
            reason="ability_not_found",
        )

    def _invoke_catalogue(
        self, *, node: str | None, request: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        target = self._system_target("meta.list_abilities", node=node)
        return _dict(self._client.invoke(target, **dict(request)).result())

    def _system_target(self, ability: str, *, node: str | None) -> Any:
        if node is None or node.strip() == "" or node.strip() == "local":
            return self._client.target(ability)
        return self._client.target(ability, owner_ura=self._device_owner(node))

    def _device_owner(self, node: str) -> str:
        return self._client.device(node).owner_ura

    def _identity(self) -> LocalIdentity:
        return self._client._who()


class AgentControl:
    """Daemon-owned agent lifecycle facade."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or _new_client()

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

        response = self._client.invoke(
            "agent.start",
            name=agent_name,
            agent_type=runtime,
            model=model,
            model_present=True,
            label=label,
            command=command,
            command_args=list(args),
            materialize_directory=True,
            update_existing_spec=False,
            project_workspace=True,
        ).result()
        return AgentStartResult.from_wire(
            _dict(response), name=agent_name, runtime=runtime
        )

    def list(self) -> builtins.list[AgentRecord]:
        response = _dict(self._client.invoke("agent.list").result())
        agents = response.get("agents") or []
        if not isinstance(agents, list):
            raise InvalidArgument(
                "agent.list response field 'agents' is not a list",
                reason="invalid_agent_list_response",
            )
        return [AgentRecord.from_wire(_dict(row)) for row in agents]

    def refresh(self, name: str | None = None) -> Mapping[str, Any]:
        agent_name = name.strip() if name is not None else None
        if name is not None and not agent_name:
            raise InvalidArgument(
                "agent name must not be empty", reason="empty_agent_name"
            )
        payload = {"name": agent_name} if agent_name else {}
        return _dict(self._client.invoke("agent.refresh", **payload).result())


class LocalFilesystemResourceRefFactory:
    """Mint short-lived daemon-local filesystem ResourceRefs.

    This is the Python equivalent of EasyNet-Cli
    `resource_ref_for_local_path`. It is intentionally narrow: only the
    `ability.deploy` read path uses it today.
    """

    def __init__(self, identity: LocalIdentity) -> None:
        self._identity = identity

    def for_path(self, path: Path, *, capability: str) -> dict[str, Any]:
        virtual_root, relative = _map_local_path(path)
        expires = int(time.time() * 1000) + _RESOURCE_REF_TTL_MS
        owner = self._identity.device_ura
        resource = resource_ura(
            self._identity.realm,
            f"device.{self._identity.node_id}",
            f"{_RESOURCE_NAMESPACE_FS}/{virtual_root}/{relative}",
        )
        return {
            "resource_ura": resource,
            "owner_ura": owner,
            "namespace": _RESOURCE_NAMESPACE_FS,
            "display_path": f"{virtual_root}/{relative}",
            "capability": capability,
            "expires_unix_ms": expires,
            "revision": _RESOURCE_REF_REVISION,
        }


def _map_local_path(path: Path) -> tuple[str, str]:
    absolute = path if path.is_absolute() else Path.cwd() / path
    try:
        resolved = absolute.resolve(strict=True)
    except FileNotFoundError as exc:
        raise InvalidArgument(
            f"resource path does not exist: {path}",
            reason="resource_path_missing",
        ) from exc

    roots = (
        ("workspace", Path.cwd()),
        ("tmp", Path(tempfile.gettempdir())),
        ("home", Path.home()),
    )
    for label, root in roots:
        try:
            root_resolved = root.resolve(strict=True)
        except FileNotFoundError:
            continue
        try:
            relative = resolved.relative_to(root_resolved)
        except ValueError:
            continue
        wire = relative.as_posix()
        _validate_relative_resource_path(wire)
        return label, wire
    raise InvalidArgument(
        f"resource path {path} is outside workspace, temp, and home roots",
        reason="resource_path_outside_virtual_roots",
    )


def _validate_relative_resource_path(value: str) -> None:
    if not value or value.startswith("/") or "\\" in value:
        raise InvalidArgument(
            f"invalid resource relative path {value!r}",
            reason="invalid_resource_path",
        )
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise InvalidArgument(
            f"invalid resource relative path {value!r}",
            reason="invalid_resource_path",
        )


def _validated_ability_ura(value: str) -> str:
    trimmed = _validated_non_empty_ura(value, "ability_ura")
    try:
        parsed = axon_ura.parse_ura(trimmed)
    except axon_ura.ParseError as exc:
        raise InvalidArgument(
            f"invalid Ability URA {trimmed!r}: {exc}",
            reason="invalid_ability_ura",
        ) from exc
    if str(parsed.kind) != "ability":
        raise InvalidArgument(
            f"expected an Ability URA, got {trimmed!r}",
            reason="invalid_ability_ura",
        )
    return trimmed


def _validated_owner_ura(value: str) -> str:
    trimmed = _validated_non_empty_ura(value, "owner_ura")
    try:
        parsed = axon_ura.parse_ura(trimmed)
    except axon_ura.ParseError as exc:
        raise InvalidArgument(
            f"invalid owner URA {trimmed!r}: {exc}",
            reason="invalid_owner_ura",
        ) from exc
    if str(parsed.kind) not in {"device", "agent", "hub", "user"}:
        raise InvalidArgument(
            f"expected an owner URA, got {trimmed!r}",
            reason="invalid_owner_ura",
        )
    return trimmed


def _validated_non_empty_ura(value: str, label: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise InvalidArgument(f"{label} must not be empty", reason=f"empty_{label}")
    return trimmed


def _list_payload(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    abilities = response.get("abilities") or []
    if not isinstance(abilities, list):
        raise InvalidArgument(
            "meta.list_abilities response field 'abilities' is not a list",
            reason="invalid_ability_list_response",
        )
    return [_dict(row) for row in abilities]


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
        parsed = axon_ura.parse_ura(record.owner_ura)
    except axon_ura.ParseError:
        return False
    if str(parsed.kind) == "user":
        return record.owner_ura.rstrip("/").endswith(f"/user/{user_id}")
    if str(parsed.kind) != "agent":
        return False
    marker = "/agent/"
    _, _, tail = record.owner_ura.partition(marker)
    return tail.split(".", 1)[0] == user_id


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
