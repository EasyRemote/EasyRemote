"""Ability addressing helpers for the Python facade.

This module projects user-facing EasyRemote targets into the explicit
Invocation tuple fields that libeasynet_cli requires. It may use Axon's
canonical URA parser, but it must not consult daemon product state on disk
or shell out to CLI commands; route policy stays inside easynet-daemon.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from easynet_axon import ura as axon_ura

from .errors import InvalidArgument
from .identity import LocalIdentity, device_ura

PICK_POLICIES = frozenset({"round_robin", "random"})


class Candidate(Protocol):
    @property
    def qualified_name(self) -> str: ...

    @property
    def input_schema(self) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class ResolvedAbility:
    """One concrete invocation target plus its argument schema."""

    callee: str
    ability: str
    input_schema: dict[str, Any] | None = None
    ability_ura: str | None = None
    subject: str | None = None
    argument_label: str | None = None


def is_ability_ura(value: str) -> bool:
    """Return true only for canonical EasyNet Ability URAs."""
    try:
        parsed = axon_ura.parse_ura(value.strip())
    except axon_ura.ParseError:
        return False
    return str(parsed.kind) == "ability"


def _is_owner_ura(value: str) -> bool:
    try:
        parsed = axon_ura.parse_ura(value.strip())
    except axon_ura.ParseError:
        return False
    return str(parsed.kind) in {"agent", "device", "hub"}


class AbilityAddressResolver:
    """Resolve EasyRemote target syntax without owning daemon routing policy."""

    def __init__(self, namespace: str) -> None:
        self._namespace = namespace

    def namespaced(self, function: str) -> str:
        """Apply the client namespace without guessing daemon-owned aliases."""
        if is_ability_ura(function) or "." in function:
            return function
        if _is_owner_ura(self._namespace):
            ability_ura = axon_ura.owner_ability_ura(self._namespace, function)
            if not isinstance(ability_ura, str):
                raise InvalidArgument(
                    f"cannot derive Ability URA for owner namespace {self._namespace!r}"
                    f" and function {function!r}",
                    reason="invalid_owner_namespace",
                )
            return ability_ura
        return f"{self._namespace}.{function}"

    def resolve(
        self,
        function: str,
        *,
        identity: LocalIdentity,
        node: str | None,
        pick: str | None,
        schemas: Mapping[str, dict[str, Any]],
        schemas_by_ura: Mapping[str, dict[str, Any]],
        candidates: Mapping[str, Sequence[Candidate]],
        round_robin: MutableMapping[str, int],
    ) -> ResolvedAbility:
        function = self.namespaced(function)
        if is_ability_ura(function):
            if node is not None or pick is not None:
                raise InvalidArgument(
                    "a canonical Ability URA already names the callable;"
                    " do not combine it with node or pick",
                    reason="target_override_for_ability_ura",
                )
            return self.from_ability_ura(
                function,
                input_schema=schemas_by_ura.get(function),
                argument_label=function,
            )

        ability = function
        verb = ability.rsplit(".", 1)[-1]
        if node is not None:
            return ResolvedAbility(
                callee=device_ura(identity.realm, node),
                ability=ability,
                input_schema=schemas.get(verb),
                argument_label=ability,
            )
        if pick is not None:
            selected = self._pick(
                verb,
                pick,
                schemas_by_ura=schemas_by_ura,
                candidates=candidates,
                round_robin=round_robin,
            )
            if selected is not None:
                return selected
        return ResolvedAbility(
            callee=identity.device_ura,
            ability=ability,
            input_schema=schemas.get(verb),
            argument_label=ability,
        )

    @staticmethod
    def from_ability_ura(
        ability_ura: str,
        *,
        input_schema: dict[str, Any] | None = None,
        argument_label: str | None = None,
    ) -> ResolvedAbility:
        try:
            parsed = axon_ura.parse_ura(ability_ura)
        except axon_ura.ParseError as exc:
            raise InvalidArgument(
                f"invalid Ability URA {ability_ura!r}: {exc}",
                reason="invalid_ability_ura",
            ) from exc
        if parsed.kind != "ability" or parsed.ability is None:
            raise InvalidArgument(
                f"expected an Ability URA, got {ability_ura!r}",
                reason="invalid_ability_ura",
            )

        owner = parsed.ability.owner
        if owner.kind == "device":
            assert isinstance(owner, axon_ura.DeviceOwner)
            callee = device_ura(parsed.realm, owner.device_id)
        elif owner.kind == "agent":
            assert isinstance(owner, axon_ura.AgentOwner)
            callee = (
                f"{axon_ura.URA_SCHEME}{parsed.realm}/agent/"
                f"{owner.user_id}.{owner.agent_id}"
            )
        elif owner.kind == "hub":
            callee = f"{axon_ura.URA_SCHEME}{parsed.realm}/hub"
        else:  # pragma: no cover - future Axon owner variants
            raise InvalidArgument(
                f"unsupported Ability URA owner {owner.kind!r}",
                reason="unsupported_ability_owner",
            )

        ability = (
            f"{parsed.ability.namespace}.{parsed.ability.local_name}"
            if parsed.ability.namespace
            else parsed.ability.local_name
        )
        return ResolvedAbility(
            callee=callee,
            ability=ability,
            input_schema=input_schema,
            ability_ura=ability_ura,
            subject=ability_ura,
            argument_label=argument_label or ability_ura,
        )

    def _pick(
        self,
        verb: str,
        policy: str,
        *,
        schemas_by_ura: Mapping[str, dict[str, Any]],
        candidates: Mapping[str, Sequence[Candidate]],
        round_robin: MutableMapping[str, int],
    ) -> ResolvedAbility | None:
        if policy not in PICK_POLICIES:
            raise InvalidArgument(
                f"pick must be one of {sorted(PICK_POLICIES)}, got {policy!r}"
                " (resource_aware needs daemon-side load metrics — Cli PR-3)",
                reason="invalid_pick_policy",
            )
        group = candidates.get(verb, ())
        if not group:
            return None
        if policy == "random":
            info = random.choice(group)
        else:
            index = round_robin.get(verb, 0)
            round_robin[verb] = index + 1
            info = group[index % len(group)]
        return self.from_ability_ura(
            info.qualified_name,
            input_schema=info.input_schema or schemas_by_ura.get(info.qualified_name),
            argument_label=info.qualified_name,
        )
