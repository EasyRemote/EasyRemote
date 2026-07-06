"""SDK-backed identity and addressing facade.

EasyRemote consumes URA and descriptor-ref semantics through this module only.
The default implementation delegates to ``easynet_sdk``; tests may inject a
deterministic facade with the same protocol.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import easynet_sdk

EASYNET_URA_PREFIX = "easynet:///"


@dataclass(frozen=True)
class UraProjection:
    """Small EasyRemote projection of an SDK identity result."""

    kind: str
    ura: str
    realm: str = ""
    components: Mapping[str, object] | None = None

    @property
    def owner_ura(self) -> str:
        return _component_string(self.components, "owner_ura")

    @property
    def owner_kind(self) -> str:
        return _component_string(self.components, "owner_kind")

    @property
    def public_name(self) -> str:
        return _component_string(self.components, "public_name")

    @property
    def namespace(self) -> str:
        return _component_string(self.components, "namespace")

    @property
    def local_name(self) -> str:
        return _component_string(self.components, "local_name")


@dataclass(frozen=True)
class DescriptorProjection:
    """EasyRemote view of an SDK DescriptorRef projection."""

    kind: str
    valid: bool
    profile: str
    components: Mapping[str, object]
    metadata: Mapping[str, object]
    descriptor_ref: str
    ability_ura: str
    descriptor_version: str


class IdentityFacadeError(Exception):
    """SDK identity failure normalized for EasyRemote callers."""

    def __init__(self, message: str, *, invalid_argument: bool = False) -> None:
        super().__init__(message)
        self.invalid_argument = invalid_argument


class IdentityFacade(Protocol):
    def parse_ura(self, value: str) -> UraProjection: ...

    def device_ura(self, realm: str, node_id: str) -> str: ...

    def agent_ura(self, realm: str, owner_token: str) -> str: ...

    def hub_ura(self, realm: str) -> str: ...

    def resource_ura(self, realm: str, owner_id: str, path: str) -> str: ...

    def device_ability_ura(
        self, realm: str, node_id: str, namespace: str, local_name: str
    ) -> str: ...

    def owner_ability_ura(self, owner_ura: str, ability_name: str) -> str: ...

    def owner_ura_for_ability(self, ability_ura: str) -> str: ...

    def canonical_ability_descriptor_ref(
        self, value: str, descriptor_version: str = ""
    ) -> str: ...

    def project_descriptor_ref(self, value: str) -> DescriptorProjection: ...


class SdkIdentityFacade:
    """Production facade over EasyNet-Cli's Python SDK identity helpers."""

    def parse_ura(self, value: str) -> UraProjection:
        try:
            projection = easynet_sdk.parse_ura(value)
        except easynet_sdk.SDKError as exc:
            raise _identity_error(exc) from exc
        return _projection(projection)

    def device_ura(self, realm: str, node_id: str) -> str:
        try:
            return easynet_sdk.device_ura(realm, node_id)
        except easynet_sdk.SDKError as exc:
            raise _identity_error(exc) from exc

    def agent_ura(self, realm: str, owner_token: str) -> str:
        user_id, agent_id = _split_agent_owner_token(owner_token)
        try:
            return easynet_sdk.agent_ura(realm, user_id, agent_id)
        except easynet_sdk.SDKError as exc:
            raise _identity_error(exc) from exc

    def hub_ura(self, realm: str) -> str:
        try:
            return easynet_sdk.hub_ura(realm)
        except easynet_sdk.SDKError as exc:
            raise _identity_error(exc) from exc

    def resource_ura(self, realm: str, owner_id: str, path: str) -> str:
        owner = self._owner_ura_from_resource_owner_id(realm, owner_id)
        try:
            return easynet_sdk.resource_ura(owner, path)
        except easynet_sdk.SDKError as exc:
            raise _identity_error(exc) from exc

    def device_ability_ura(
        self, realm: str, node_id: str, namespace: str, local_name: str
    ) -> str:
        try:
            return easynet_sdk.device_ability_ura(realm, node_id, namespace, local_name)
        except easynet_sdk.SDKError as exc:
            raise _identity_error(exc) from exc

    def owner_ability_ura(self, owner_ura: str, ability_name: str) -> str:
        try:
            return easynet_sdk.owner_ability_ura(owner_ura, ability_name)
        except easynet_sdk.SDKError as exc:
            raise _identity_error(exc) from exc

    def owner_ura_for_ability(self, ability_ura: str) -> str:
        try:
            return easynet_sdk.owner_ura_for_ability(ability_ura)
        except easynet_sdk.SDKError as exc:
            raise _identity_error(exc) from exc

    def canonical_ability_descriptor_ref(
        self, value: str, descriptor_version: str = ""
    ) -> str:
        try:
            return easynet_sdk.canonical_ability_descriptor_ref(
                value,
                descriptor_version,
            )
        except easynet_sdk.SDKError as exc:
            raise _identity_error(exc) from exc

    def project_descriptor_ref(self, value: str) -> DescriptorProjection:
        try:
            projection = easynet_sdk.project_descriptor_ref(value)
        except easynet_sdk.SDKError as exc:
            raise _identity_error(exc) from exc
        return _descriptor_projection(projection)

    def _owner_ura_from_resource_owner_id(self, realm: str, owner_id: str) -> str:
        owner_id = owner_id.strip()
        if owner_id.startswith("device."):
            return self.device_ura(realm, owner_id.removeprefix("device."))
        raise IdentityFacadeError(
            f"unsupported resource owner id {owner_id!r}",
            invalid_argument=True,
        )


_facade: IdentityFacade = SdkIdentityFacade()


def identity_facade() -> IdentityFacade:
    return _facade


def set_identity_facade_for_tests(facade: IdentityFacade) -> None:
    global _facade
    _facade = facade


def reset_identity_facade_for_tests() -> None:
    global _facade
    _facade = SdkIdentityFacade()


def parse_ura(value: str) -> UraProjection:
    return identity_facade().parse_ura(value)


def is_easynet_ura_text(value: str) -> bool:
    return value.strip().startswith(EASYNET_URA_PREFIX)


def device_ura(realm: str, node_id: str) -> str:
    return identity_facade().device_ura(realm, node_id)


def agent_ura(realm: str, owner_token: str) -> str:
    return identity_facade().agent_ura(realm, owner_token)


def hub_ura(realm: str) -> str:
    return identity_facade().hub_ura(realm)


def resource_ura(realm: str, owner_id: str, path: str) -> str:
    return identity_facade().resource_ura(realm, owner_id, path)


def device_ability_ura(
    realm: str, node_id: str, namespace: str, local_name: str
) -> str:
    return identity_facade().device_ability_ura(realm, node_id, namespace, local_name)


def owner_ability_ura(owner_ura: str, ability_name: str) -> str:
    return identity_facade().owner_ability_ura(owner_ura, ability_name)


def owner_ura_for_ability(ability_ura: str) -> str:
    return identity_facade().owner_ura_for_ability(ability_ura)


def canonical_ability_descriptor_ref(
    value: str, descriptor_version: str = ""
) -> str:
    return identity_facade().canonical_ability_descriptor_ref(
        value,
        descriptor_version,
    )


def project_descriptor_ref(value: str) -> DescriptorProjection:
    return identity_facade().project_descriptor_ref(value)


def _projection(projection: easynet_sdk.IdentityProjection) -> UraProjection:
    return UraProjection(
        kind=projection.kind,
        ura=projection.ura,
        realm=projection.realm,
        components=projection.components,
    )


def _descriptor_projection(
    projection: easynet_sdk.IdentityProjection,
) -> DescriptorProjection:
    return DescriptorProjection(
        kind=projection.kind,
        valid=projection.valid,
        profile=projection.profile,
        components=projection.components,
        metadata=projection.metadata,
        descriptor_ref=projection.descriptor_ref,
        ability_ura=projection.ability_ura,
        descriptor_version=projection.descriptor_version,
    )


def _identity_error(exc: easynet_sdk.SDKError) -> IdentityFacadeError:
    invalid = exc.code == easynet_sdk.ErrorCode.INVALID_ARGUMENT
    return IdentityFacadeError(str(exc), invalid_argument=invalid)


def _split_agent_owner_token(owner_token: str) -> tuple[str, str]:
    user_id, separator, agent_id = owner_token.strip().partition(".")
    if not user_id or not separator or not agent_id:
        raise IdentityFacadeError(
            f"agent owner token must be '<user-id>.<agent-id>', got {owner_token!r}",
            invalid_argument=True,
        )
    return user_id, agent_id


def _component_string(
    components: Mapping[str, object] | None, field: str
) -> str:
    value = (components or {}).get(field)
    return value if isinstance(value, str) else ""
