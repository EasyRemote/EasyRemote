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

import easynet_sdk

from . import _sdk_identity
from ._product_abilities import AgentAbility
from .errors import InvalidArgument, RemoteError, Unavailable, error_from_sdk

if TYPE_CHECKING:
    from .client import Client

__all__ = [
    "AbilityControl",
    "AbilityInstallResult",
    "AbilityRecord",
    "AgentControl",
    "AgentRecord",
    "AgentStartResult",
    "AgentStopResult",
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
        metadata = _optional_dict(value.get("metadata"))
        return cls(
            name=str(value.get("name") or ""),
            runtime=str(
                value.get("runtime")
                or value.get("kind")
                or value.get("agent_type")
                or ""
            ),
            model=_optional_str(value.get("model")),
            root_path=_optional_str(value.get("root_path", metadata.get("root_path"))),
            timeout_secs=_optional_int(
                value.get("timeout_secs", metadata.get("timeout_secs"))
            ),
            root_exists=_optional_bool(
                value.get("root_exists", metadata.get("root_exists"))
            ),
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


@dataclass(frozen=True)
class AgentStopResult:
    """Daemon response from `agent.stop`."""

    name: str
    agent_ura: str | None
    stopped: bool
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_wire(
        cls,
        value: Mapping[str, Any],
        *,
        name: str,
    ) -> AgentStopResult:
        return cls(
            name=str(value.get("name") or name),
            agent_ura=_optional_str(value.get("agent_ura")),
            stopped=bool(value.get("stopped", value.get("ack", False))),
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
            raise InvalidArgument("node must not be empty", reason="empty_node")
        package = Path(path)
        if not package.is_dir():
            raise InvalidArgument(
                f"ability package path is not a directory: {package}",
                reason="ability_package_not_directory",
            )
        ref = _local_resource_ref(package, self._client._who())
        result = self._invoke(
            self._client.target("ability.deploy", subject=str(ref["resource_ura"])),
            resource_ref=ref,
            node_id=node_id,
        )
        return AbilityInstallResult.from_wire(result, node_id=node_id)

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
        if scope not in {"local", "realm"}:
            raise InvalidArgument("unsupported ability list scope", reason="invalid_ability_scope")
        args: dict[str, object] = {}
        if scope == "realm":
            args["scope"] = scope
        if owner_ura:
            _require_ura_kind(owner_ura, {"device", "agent", "hub", "user"}, "owner_ura")
            args["agent_ura"] = owner_ura
        if subject_ura:
            _require_ura_kind(subject_ura, {"ability"}, "subject_ura")
            args["subject_ura"] = subject_ura
        owner = self._client._who().device_ura if not node else self._client.device(node).owner_ura
        result = self._invoke(self._client.target("meta.list_abilities", owner_ura=owner), **args)
        rows = result.get("abilities") or []
        if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
            raise InvalidArgument("meta.list_abilities response field 'abilities' is not an object array", reason="invalid_daemon_response")
        records = [AbilityRecord.from_wire(row) for row in rows if isinstance(row, Mapping)]
        if user_id:
            user = user_id.strip()
            if not user:
                raise InvalidArgument("user_id must not be empty", reason="empty_user_id")
            records = [record for record in records if _record_belongs_to_user(record, user)]
        return records

    def list_device(self, device: str | None = None) -> builtins.list[AbilityRecord]:
        """List abilities owned by this device, or another device owner."""
        owner = self._client._who().device_ura if device is None else self._client.device(device).owner_ura
        return self.list(owner_ura=owner)

    def list_user(
        self,
        user_id: str | None = None,
        *,
        scope: AbilityListScope = "realm",
    ) -> builtins.list[AbilityRecord]:
        """List abilities owned by this paired user across catalogue rows."""
        user = user_id if user_id is not None else self._client._who().username
        if not user or not user.strip():
            raise InvalidArgument("user_id is required because credentials have no username", reason="missing_user_id")
        return self.list(user_id=user.strip(), scope=scope)

    def show(
        self,
        ability_ura: str,
        *,
        node: str | None = None,
        scope: AbilityListScope = "local",
    ) -> AbilityRecord:
        """Return one ability catalogue row by canonical Ability URA."""
        _require_ura_kind(ability_ura, {"ability"}, "ability_ura")
        for record in self.list(node=node, subject_ura=ability_ura, scope=scope):
            if record.ability_ura == ability_ura:
                return record
        raise Unavailable(
            f"ability {ability_ura!r} was not found in the daemon catalogue",
            reason="ability_not_found",
        )

    def _invoke(self, target: object, **kwargs: object) -> dict[str, Any]:
        try:
            result = self._client.invoke(target, **kwargs).result()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc
        except RemoteError:
            raise
        except Exception as exc:
            raise Unavailable(f"ability control invocation failed: {exc}", reason="ability_invocation_failed") from exc
        return _dict(result)


class AgentControl:
    """EasyRemote product facade for daemon-owned agent lifecycle."""

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

        result = self._invoke(
            AgentAbility.START,
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
        )
        return AgentStartResult.from_wire(
            result,
            name=agent_name,
            runtime=runtime,
        )

    def list(self) -> builtins.list[AgentRecord]:
        result = self._invoke(AgentAbility.LIST)
        rows = result.get("agents")
        if not isinstance(rows, list) or not all(
            isinstance(row, Mapping) for row in rows
        ):
            raise InvalidArgument(
                "agent.list result must contain an agents object array",
                reason="invalid_daemon_response",
            )
        return [AgentRecord.from_wire(row) for row in rows if isinstance(row, Mapping)]

    def stop(self, name: str) -> AgentStopResult:
        agent_name = name.strip()
        if not agent_name:
            raise InvalidArgument(
                "agent name must not be empty",
                reason="empty_agent_name",
            )
        return AgentStopResult.from_wire(
            self._invoke(AgentAbility.STOP, name=agent_name),
            name=agent_name,
        )

    def refresh(self, name: str | None = None) -> Mapping[str, Any]:
        args: dict[str, object] = {}
        if name is not None:
            agent_name = name.strip()
            if not agent_name:
                raise InvalidArgument(
                    "agent name must not be empty",
                    reason="empty_agent_name",
                )
            args["name"] = agent_name
        return self._invoke(AgentAbility.REFRESH, **args)

    def _invoke(
        self,
        ability: AgentAbility,
        **kwargs: object,
    ) -> dict[str, Any]:
        try:
            result = self._client.invoke(str(ability), **kwargs).result()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc
        except RemoteError:
            raise
        except Exception as exc:
            raise Unavailable(
                f"{ability} invocation failed: {exc}",
                reason="agent_invocation_failed",
            ) from exc
        if not isinstance(result, Mapping):
            raise InvalidArgument(
                f"{ability} result must be an object",
                reason="invalid_daemon_response",
            )
        return dict(result)


def _local_resource_ref(path: Path, identity: object) -> dict[str, object]:
    absolute = path if path.is_absolute() else Path.cwd() / path
    resolved = absolute.resolve(strict=True)
    for label, root in (("workspace", Path.cwd()), ("tmp", Path(tempfile.gettempdir())), ("home", Path.home())):
        try:
            relative = resolved.relative_to(root.resolve(strict=True)).as_posix()
        except (FileNotFoundError, ValueError):
            continue
        if relative and all(part not in {"", ".", ".."} for part in relative.split("/")):
            owner = str(getattr(identity, "device_ura"))
            resource = _sdk_identity.resource_ura(owner, f"fs/{label}/{relative}")
            return {
                "resource_ura": resource,
                "owner_ura": owner,
                "namespace": "fs",
                "capability": "read",
                "expires_unix_ms": int(time.time() * 1000) + 300_000,
                "revision": "fs-local-mapping-v1",
                "display_path": f"{label}/{relative}",
            }
    raise InvalidArgument(f"resource path {path} is outside workspace, temp, and home roots", reason="invalid_resource_path")


def _require_ura_kind(value: str, kinds: set[str], field: str) -> None:
    candidate = value.strip()
    if not candidate:
        raise InvalidArgument(f"{field} must not be empty", reason=f"empty_{field}")
    try:
        projection = _sdk_identity.parse_ura(candidate)
    except _sdk_identity.IdentityFacadeError as exc:
        raise InvalidArgument(f"invalid {field}: {exc}", reason=f"invalid_{field}") from exc
    if projection.kind not in kinds:
        raise InvalidArgument(f"unexpected {field} kind {projection.kind!r}", reason=f"invalid_{field}")


def _record_belongs_to_user(record: AbilityRecord, user_id: str) -> bool:
    if any(str(record.metadata.get(key) or "") == user_id for key in ("owner_user", "owner_user_id", "user_id", "local_user_id")):
        return True
    try:
        owner = _sdk_identity.parse_ura(record.owner_ura)
    except _sdk_identity.IdentityFacadeError:
        return False
    components = owner.components or {}
    return owner.kind in {"agent", "user"} and str(components.get("user_id") or "") == user_id


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
