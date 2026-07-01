"""Ability addressing helpers for the Python facade.

This module projects user-facing EasyRemote targets into the explicit
Invocation tuple fields that libeasynet_cli requires. It may use Axon's
canonical URA parser, but it must not consult daemon product state on disk
or shell out to CLI commands; route policy stays inside easynet-daemon.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from easynet_axon import ura as axon_ura

from .errors import InvalidArgument
from .identity import LocalIdentity, device_ura

PICK_POLICIES = frozenset({"round_robin", "random"})
CallCarrier = Literal["stream", "unary"]


class Candidate(Protocol):
    @property
    def name(self) -> str: ...  # verb, e.g. "ai_inference"

    @property
    def qualified_name(self) -> str: ...  # full ability URA

    @property
    def input_schema(self) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class ResolvedAbility:
    """One concrete invocation target plus its argument schema."""

    callee: str
    ability: str
    call_carrier: CallCarrier
    input_schema: dict[str, Any] | None = None
    ability_ura: str | None = None
    subject: str | None = None
    argument_label: str | None = None


class DiscoveryCache:
    """Discovery results plus the round-robin selection cursor.

    ``functions()`` populates one of these from a ``discover`` response;
    targeting reads it back. The selection cursor lives here — the one
    place that owns mutable selection state — so no collaborator has to
    thread a cursor dict through every call. An empty cache (no discovery
    run yet) simply has no candidates and falls back to local addressing.
    """

    def __init__(self) -> None:
        self._schemas: dict[str, dict[str, Any]] = {}  # unambiguous verb → schema
        self._schemas_by_ura: dict[str, dict[str, Any]] = {}
        self._candidates: dict[str, list[Candidate]] = {}  # verb → discover hits
        self._round_robin: dict[str, int] = {}

    def replace(self, candidates: Iterable[Candidate]) -> None:
        """Adopt a fresh discovery result, discarding the prior one.

        A bare verb schema is cached only when every owner advertising
        that verb agrees on it: two devices may expose the same verb with
        different parameter order, so an ambiguous verb stays schema-less
        until owner selection pins one candidate.
        """
        self._schemas.clear()
        self._schemas_by_ura.clear()
        self._candidates.clear()
        self._round_robin.clear()
        for info in candidates:
            if info.name and info.qualified_name:
                self._candidates.setdefault(info.name, []).append(info)
            if info.qualified_name and info.input_schema:
                self._schemas_by_ura[info.qualified_name] = info.input_schema
        for verb, group in self._candidates.items():
            schemas = [info.input_schema for info in group]
            if schemas and all(s and s == schemas[0] for s in schemas):
                assert schemas[0] is not None
                self._schemas[verb] = schemas[0]

    def schema_for_verb(self, verb: str) -> dict[str, Any] | None:
        return self._schemas.get(verb)

    def schema_for_ura(self, ability_ura: str) -> dict[str, Any] | None:
        return self._schemas_by_ura.get(ability_ura)

    def select(self, verb: str, policy: str) -> Candidate | None:
        """Pick one discovered candidate for ``verb`` under ``policy``.

        O(1) per call: candidates are pre-grouped by verb, so selection
        is a single index/choice, not a scan of the discovery result.
        """
        group = self._candidates.get(verb, ())
        if not group:
            return None
        if policy == "random":
            return random.choice(group)
        index = self._round_robin.get(verb, 0)
        self._round_robin[verb] = index + 1
        return group[index % len(group)]


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
    """Resolve EasyRemote target syntax without owning daemon routing policy.

    Holds the per-client :class:`DiscoveryCache` (populated by
    ``functions()``) so targeting reads discovery results and the
    round-robin cursor from one owner instead of parallel client dicts.
    """

    def __init__(self, namespace: str) -> None:
        self._namespace = namespace
        self.cache = DiscoveryCache()

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
        owner_ura: str | None = None,
    ) -> ResolvedAbility:
        if owner_ura is not None:
            return self._resolve_owner(function, owner_ura)
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
                input_schema=self.cache.schema_for_ura(function),
                argument_label=function,
            )

        ability = function
        verb = ability.rsplit(".", 1)[-1]
        if node is not None:
            return ResolvedAbility(
                callee=device_ura(identity.realm, node),
                ability=ability,
                call_carrier="stream",
                input_schema=self.cache.schema_for_verb(verb),
                argument_label=ability,
            )
        if pick is not None:
            selected = self._pick(verb, pick)
            if selected is not None:
                return selected
        return ResolvedAbility(
            callee=identity.device_ura,
            ability=ability,
            call_carrier="stream",
            input_schema=self.cache.schema_for_verb(verb),
            argument_label=ability,
        )

    def _resolve_owner(self, function: str, owner_ura: str) -> ResolvedAbility:
        """Resolve a function against an explicit owner handle.

        A full Ability URA passes through verbatim. A short name is
        namespaced (a bare verb gets this client's namespace, a dotted name
        passes through) and projected onto the owner via Axon's
        ``owner_ability_ura`` — so the callee Axon later derives from the
        Ability URA is exactly this owner, satisfying the daemon's
        owner == callee descriptor binding.
        """
        if is_ability_ura(function):
            return self.from_ability_ura(
                function,
                input_schema=self.cache.schema_for_ura(function),
                argument_label=function,
            )
        ability_name = function if "." in function else f"{self._namespace}.{function}"
        ability_ura = axon_ura.owner_ability_ura(owner_ura, ability_name)
        if not isinstance(ability_ura, str):
            raise InvalidArgument(
                f"owner {owner_ura!r} cannot publish abilities (users own none;"
                " ability owners are device, agent, or hub)",
                reason="invalid_owner_for_ability",
            )
        return self.from_ability_ura(
            ability_ura,
            input_schema=self.cache.schema_for_ura(ability_ura),
            argument_label=ability_ura,
            call_carrier=_call_carrier_for_owner(owner_ura),
        )

    @staticmethod
    def from_ability_ura(
        ability_ura: str,
        *,
        input_schema: dict[str, Any] | None = None,
        argument_label: str | None = None,
        call_carrier: CallCarrier | None = None,
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

        # The callee is the ability owner. Axon owns that derivation (it
        # is the same `AbilitySelector::owner_ura()` the daemon uses to
        # check owner == callee); the facade must not re-derive it from
        # owner kinds, or the two could disagree as Axon owners evolve.
        callee = axon_ura.owner_ura_for_ability(ability_ura)
        if callee is None:  # pragma: no cover - parse already proved ability
            raise InvalidArgument(
                f"cannot derive callee owner for Ability URA {ability_ura!r}",
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
            call_carrier=call_carrier or _call_carrier_for_owner(callee),
            input_schema=input_schema,
            ability_ura=ability_ura,
            subject=ability_ura,
            argument_label=argument_label or ability_ura,
        )

    def _pick(self, verb: str, policy: str) -> ResolvedAbility | None:
        if policy not in PICK_POLICIES:
            raise InvalidArgument(
                f"pick must be one of {sorted(PICK_POLICIES)}, got {policy!r}"
                " (resource_aware needs daemon-side load metrics — Cli PR-3)",
                reason="invalid_pick_policy",
            )
        info = self.cache.select(verb, policy)
        if info is None:
            return None
        return self.from_ability_ura(
            info.qualified_name,
            input_schema=info.input_schema
            or self.cache.schema_for_ura(info.qualified_name),
            argument_label=info.qualified_name,
        )


def owner_kind(owner_ura: str) -> str:
    """The canonical owner kind for a device/agent/hub owner URA."""
    try:
        parsed = axon_ura.parse_ura(owner_ura.strip())
    except axon_ura.ParseError as exc:
        raise InvalidArgument(
            f"invalid owner URA {owner_ura!r}: {exc}",
            reason="invalid_owner_ura",
        ) from exc
    kind = str(parsed.kind)
    if kind not in {"device", "agent", "hub"}:
        raise InvalidArgument(
            f"owner {owner_ura!r} cannot publish abilities (users own none;"
            " ability owners are device, agent, or hub)",
            reason="invalid_owner_for_ability",
        )
    return kind


def _call_carrier_for_owner(owner_ura: str) -> CallCarrier:
    return "stream" if owner_kind(owner_ura) == "device" else "unary"
