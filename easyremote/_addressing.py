"""EasyRemote target selection over the canonical SDK Addressing provider."""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import easynet_sdk

from .errors import InvalidArgument
from .identity import LocalIdentity

PICK_POLICIES = frozenset({"round_robin", "random"})
CallCarrier = Literal["stream", "unary"]


class Candidate(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def ability_ura(self) -> str: ...

    @property
    def input_schema(self) -> Mapping[str, Any] | None: ...

    @property
    def descriptor_ref(self) -> str: ...


@dataclass(frozen=True)
class ResolvedAbility:
    """Product selection facts consumed by the SDK Invocation provider."""

    ability_ura: str
    resolved_subject_ura: str
    call_carrier: CallCarrier
    input_schema: dict[str, Any] | None = None
    argument_label: str | None = None
    descriptor_ref: str = ""


class DiscoveryCache:
    """Discovery results plus one owned round-robin cursor."""

    def __init__(self) -> None:
        self._schemas: dict[str, dict[str, Any]] = {}
        self._schemas_by_ura: dict[str, dict[str, Any]] = {}
        self._descriptor_refs_by_ura: dict[str, str] = {}
        self._candidates: dict[str, list[Candidate]] = {}
        self._agent_owners_by_id: dict[str, set[str]] = {}
        self._round_robin: dict[str, int] = {}

    def replace(self, candidates: Iterable[Candidate]) -> None:
        self._schemas.clear()
        self._schemas_by_ura.clear()
        self._descriptor_refs_by_ura.clear()
        self._candidates.clear()
        self._agent_owners_by_id.clear()
        self._round_robin.clear()
        self.remember(candidates)

    def remember(self, candidates: Iterable[Candidate]) -> None:
        for info in candidates:
            if info.name and info.ability_ura:
                self._candidates.setdefault(info.name, []).append(info)
            if info.ability_ura and info.input_schema:
                self._schemas_by_ura[info.ability_ura] = dict(info.input_schema)
            if info.ability_ura and info.descriptor_ref:
                self._descriptor_refs_by_ura[info.ability_ura] = info.descriptor_ref
            self._remember_agent_owner(
                _candidate_owner_ura(info) or _ability_owner_ura(info.ability_ura)
            )
        for verb, group in self._candidates.items():
            schemas = [info.input_schema for info in group]
            if schemas and all(schema and schema == schemas[0] for schema in schemas):
                assert schemas[0] is not None
                self._schemas[verb] = dict(schemas[0])

    def remember_catalog_rows(self, rows: Iterable[Mapping[str, Any]]) -> None:
        for row in rows:
            self._remember_agent_owner(
                str(row.get("owner_ura") or "")
                or _ability_owner_ura(
                    str(
                        row.get("ability_ura")
                        or row.get("qualified_name")
                        or row.get("descriptor_ref")
                        or ""
                    )
                )
            )

    def agent_owner_uras(self, agent_id: str) -> tuple[str, ...]:
        return tuple(sorted(self._agent_owners_by_id.get(agent_id, ())))

    def schema_for_verb(self, verb: str) -> dict[str, Any] | None:
        return self._schemas.get(verb)

    def schema_for_ura(self, ability_ura: str) -> dict[str, Any] | None:
        return self._schemas_by_ura.get(ability_ura)

    def descriptor_ref_for_ura(self, ability_ura: str) -> str:
        return self._descriptor_refs_by_ura.get(ability_ura, "")

    def remember_descriptor(
        self,
        ability_ura: str,
        descriptor_ref: str,
        input_schema: dict[str, Any] | None = None,
    ) -> None:
        if not ability_ura or not descriptor_ref:
            return
        self._descriptor_refs_by_ura[ability_ura] = descriptor_ref
        if input_schema:
            self._schemas_by_ura[ability_ura] = dict(input_schema)
        self._remember_agent_owner(_ability_owner_ura(ability_ura))

    def select(self, verb: str, policy: str) -> Candidate | None:
        group = self._candidates.get(verb, ())
        if not group:
            return None
        if policy == "random":
            return random.choice(group)
        index = self._round_robin.get(verb, 0)
        self._round_robin[verb] = index + 1
        return group[index % len(group)]

    def _remember_agent_owner(self, owner_ura: str) -> None:
        agent_id = _agent_id(owner_ura)
        if agent_id:
            self._agent_owners_by_id.setdefault(agent_id, set()).add(owner_ura)


class AbilityAddressResolver:
    """Own EasyRemote selection state while delegating every URA fact to SDK."""

    def __init__(
        self,
        namespace: str,
        addressing: easynet_sdk.AddressingClient,
    ) -> None:
        self._namespace = namespace
        self._addressing = addressing
        self.cache = DiscoveryCache()

    def close(self) -> None:
        self._addressing.close()

    def namespaced(self, function: str) -> str:
        if self.is_ability_ura(function) or "." in function:
            return function
        if self.is_owner_ura(self._namespace):
            return self._owner_ability_ura(self._namespace, function)
        return f"{self._namespace}.{function}"

    def resolve(
        self,
        function: str,
        *,
        identity: LocalIdentity,
        node: str | None,
        pick: str | None,
        owner_ura: str | None = None,
    ) -> ResolvedAbility:
        if owner_ura is not None:
            return self._resolve_owner(function, owner_ura)
        function = self.namespaced(function)
        if self.is_ability_ura(function):
            if node is not None or pick is not None:
                raise InvalidArgument(
                    "a canonical Ability URA already names the callable;"
                    " do not combine it with node or pick",
                    reason="target_override_for_ability_ura",
                )
            return self.from_ability_ura(
                function,
                input_schema=self.cache.schema_for_ura(function),
                descriptor_ref=self.cache.descriptor_ref_for_ura(function),
                argument_label=function,
            )

        verb = function.rsplit(".", 1)[-1]
        if node is not None:
            owner = self._sdk_call(
                lambda: self._addressing.device_ura(identity.realm, node),
                reason="invalid_device_owner",
            )
            return self._resolved_short_name(function, owner, verb)
        if pick is not None:
            selected = self._pick(verb, pick)
            if selected is not None:
                return selected
        return self._resolved_short_name(function, identity.device_ura, verb)

    def _resolved_short_name(
        self,
        function: str,
        owner_ura: str,
        verb: str,
    ) -> ResolvedAbility:
        ability_ura = self._owner_ability_ura(owner_ura, function)
        return ResolvedAbility(
            ability_ura=ability_ura,
            resolved_subject_ura=owner_ura,
            call_carrier=_call_carrier_for_kind(self.owner_kind(owner_ura)),
            input_schema=self.cache.schema_for_verb(verb),
            argument_label=function,
        )

    def _resolve_owner(self, function: str, owner_ura: str) -> ResolvedAbility:
        if self.is_ability_ura(function):
            return self.from_ability_ura(
                function,
                input_schema=self.cache.schema_for_ura(function),
                descriptor_ref=self.cache.descriptor_ref_for_ura(function),
                argument_label=function,
            )
        ability_name = function if "." in function else f"{self._namespace}.{function}"
        ability_ura = self._owner_ability_ura(owner_ura, ability_name)
        return self.from_ability_ura(
            ability_ura,
            input_schema=self.cache.schema_for_ura(ability_ura),
            descriptor_ref=self.cache.descriptor_ref_for_ura(ability_ura),
            argument_label=ability_ura,
            call_carrier=_call_carrier_for_kind(self.owner_kind(owner_ura)),
        )

    def from_ability_ura(
        self,
        ability_ura: str,
        *,
        input_schema: dict[str, Any] | None = None,
        argument_label: str | None = None,
        call_carrier: CallCarrier | None = None,
        descriptor_ref: str = "",
    ) -> ResolvedAbility:
        try:
            projection = self._addressing.project_ability_ura(ability_ura)
            owner_ura = projection.owner_ura
        except easynet_sdk.SDKError as exc:
            raise InvalidArgument(
                f"invalid Ability URA {ability_ura!r}: {exc}",
                reason="invalid_ability_ura",
            ) from exc
        return ResolvedAbility(
            ability_ura=projection.ura,
            resolved_subject_ura=projection.ura,
            call_carrier=call_carrier
            or _call_carrier_for_kind(self.owner_kind(owner_ura)),
            input_schema=input_schema,
            argument_label=argument_label or projection.ura,
            descriptor_ref=descriptor_ref,
        )

    def owner_kind(self, owner_ura: str) -> str:
        try:
            kind = str(self._addressing.parse_ura(owner_ura.strip()).kind)
        except easynet_sdk.SDKError as exc:
            raise InvalidArgument(
                f"invalid owner URA {owner_ura!r}: {exc}",
                reason="invalid_owner_ura",
            ) from exc
        if kind not in {"device", "agent", "authority"}:
            raise InvalidArgument(
                f"owner {owner_ura!r} cannot publish abilities",
                reason="invalid_owner_for_ability",
            )
        return kind

    def is_ability_ura(self, value: str) -> bool:
        try:
            self._addressing.project_ability_ura(value.strip())
        except easynet_sdk.SDKError:
            return False
        return True

    def is_owner_ura(self, value: str) -> bool:
        try:
            kind = self._addressing.parse_ura(value.strip()).kind
        except easynet_sdk.SDKError:
            return False
        return kind in {"agent", "device", "authority"}

    def _owner_ability_ura(self, owner_ura: str, ability_name: str) -> str:
        return self._sdk_call(
            lambda: self._addressing.owner_ability_ura(owner_ura, ability_name),
            reason="invalid_owner_for_ability",
        )

    def owner_ability_ura(self, owner_ura: str, ability_name: str) -> str:
        return self._owner_ability_ura(owner_ura, ability_name)

    def _pick(self, verb: str, policy: str) -> ResolvedAbility | None:
        if policy not in PICK_POLICIES:
            raise InvalidArgument(
                f"pick must be one of {sorted(PICK_POLICIES)}, got {policy!r}"
                " (resource_aware needs daemon-side load metrics)",
                reason="invalid_pick_policy",
            )
        info = self.cache.select(verb, policy)
        if info is None:
            return None
        return self.from_ability_ura(
            info.ability_ura,
            input_schema=dict(info.input_schema)
            if info.input_schema
            else self.cache.schema_for_ura(info.ability_ura),
            argument_label=info.ability_ura,
            descriptor_ref=info.descriptor_ref
            or self.cache.descriptor_ref_for_ura(info.ability_ura),
        )

    @staticmethod
    def _sdk_call(operation: Any, *, reason: str) -> str:
        try:
            return str(operation())
        except easynet_sdk.SDKError as exc:
            raise InvalidArgument(str(exc), reason=reason) from exc


def canonical_addressing_client() -> easynet_sdk.AddressingClient:
    return easynet_sdk.AddressingClient(easynet_sdk.AxonAddressingTransport())


def _call_carrier_for_kind(kind: str) -> CallCarrier:
    return "stream" if kind == "device" else "unary"


def _candidate_owner_ura(candidate: Candidate) -> str:
    return str(getattr(candidate, "owner_ura", "") or "")


def _ability_owner_ura(ability_ura: str) -> str:
    if not ability_ura:
        return ""
    try:
        projection = easynet_sdk.parse_ura(ability_ura)
    except easynet_sdk.SDKError:
        return ""
    if projection.kind != "ability":
        return ""
    return str((projection.components or {}).get("owner_ura") or "")


def _agent_id(owner_ura: str) -> str:
    if not owner_ura:
        return ""
    try:
        projection = easynet_sdk.parse_ura(owner_ura)
    except easynet_sdk.SDKError:
        return ""
    if projection.kind != "agent":
        return ""
    return str((projection.components or {}).get("agent_id") or "")
