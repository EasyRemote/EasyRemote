"""Product policies that populate canonical SDK ability requests."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, final

import easynet_sdk

from .errors import InvalidArgument

__all__ = [
    "ChildCausal",
    "CompleteExplicit",
    "ExplicitSubject",
    "FreshCausal",
    "FreshContextChild",
    "FreshRoot",
    "InvocationDerivationPolicy",
    "InvocationSubjectPolicy",
    "ResolvedTargetSubject",
    "runtime_root_context",
]


class InvocationSubjectPolicy(ABC):
    """Select the product subject from resolved target facts."""

    @abstractmethod
    def select(self, resolved_subject_ura: str) -> str:
        """Return one explicit subject URA."""


@dataclass(frozen=True)
class ExplicitSubject(InvocationSubjectPolicy):
    subject_ura: str

    def select(self, resolved_subject_ura: str) -> str:
        del resolved_subject_ura
        return _subject(self.subject_ura)


@dataclass(frozen=True)
class ResolvedTargetSubject(InvocationSubjectPolicy):
    """Explicitly select the subject candidate produced by target resolution."""

    def select(self, resolved_subject_ura: str) -> str:
        return _subject(resolved_subject_ura)


class InvocationDerivationPolicy(ABC):
    """Build one SDK-owned request from EasyRemote product intent."""

    @final
    def derive(
        self,
        *,
        caller_ura: str,
        ability_ura: str,
        resolved_subject_ura: str,
        args: object,
        metadata: Mapping[str, object],
    ) -> easynet_sdk.AbilityTargetRequest:
        """Derive and validate the product-to-SDK request boundary."""
        try:
            request = self.request(
                caller_ura=caller_ura,
                ability_ura=ability_ura,
                resolved_subject_ura=resolved_subject_ura,
                args=args,
                metadata=metadata,
            )
        except InvalidArgument:
            raise
        except (TypeError, ValueError, easynet_sdk.SDKError) as exc:
            raise InvalidArgument(
                f"invocation policy is underspecified: {exc}",
                reason="invalid_invocation_derivation_policy",
            ) from exc
        if not isinstance(request, easynet_sdk.AbilityTargetRequest):
            raise InvalidArgument(
                "invocation policy must produce an SDK AbilityTargetRequest",
                reason="invalid_invocation_derivation_policy",
            )
        return request

    @abstractmethod
    def request(
        self,
        *,
        caller_ura: str,
        ability_ura: str,
        resolved_subject_ura: str,
        args: object,
        metadata: Mapping[str, object],
    ) -> easynet_sdk.AbilityTargetRequest:
        """Return the canonical SDK request DTO."""


@dataclass(frozen=True)
class CompleteExplicit(InvocationDerivationPolicy):
    subject_ura: str
    nonce_base64: str
    causal_context: Mapping[str, object]

    def request(
        self,
        *,
        caller_ura: str,
        ability_ura: str,
        resolved_subject_ura: str,
        args: object,
        metadata: Mapping[str, object],
    ) -> easynet_sdk.AbilityTargetRequest:
        del resolved_subject_ura
        return _request(
            caller_ura=caller_ura,
            ability_ura=ability_ura,
            subject_ura=self.subject_ura,
            nonce_base64=self.nonce_base64,
            causal_context=self.causal_context,
            args=args,
            metadata=metadata,
        )


@dataclass(frozen=True)
class FreshRoot(InvocationDerivationPolicy):
    """Issue a root invocation under an explicitly selected subject policy."""

    subject: InvocationSubjectPolicy

    def request(
        self,
        *,
        caller_ura: str,
        ability_ura: str,
        resolved_subject_ura: str,
        args: object,
        metadata: Mapping[str, object],
    ) -> easynet_sdk.AbilityTargetRequest:
        _require_subject_policy(self.subject)
        return _request(
            caller_ura=caller_ura,
            ability_ura=ability_ura,
            subject_ura=self.subject.select(resolved_subject_ura),
            nonce_base64=easynet_sdk.new_invocation_nonce_base64(),
            causal_context={"form": "none"},
            args=args,
            metadata=metadata,
        )


@dataclass(frozen=True)
class FreshCausal(InvocationDerivationPolicy):
    """Create a fresh invocation with an explicit causal context."""

    subject: InvocationSubjectPolicy
    causal_context: Mapping[str, object]

    def request(
        self,
        *,
        caller_ura: str,
        ability_ura: str,
        resolved_subject_ura: str,
        args: object,
        metadata: Mapping[str, object],
    ) -> easynet_sdk.AbilityTargetRequest:
        _require_subject_policy(self.subject)
        return _request(
            caller_ura=caller_ura,
            ability_ura=ability_ura,
            subject_ura=self.subject.select(resolved_subject_ura),
            nonce_base64=easynet_sdk.new_invocation_nonce_base64(),
            causal_context=self.causal_context,
            args=args,
            metadata=metadata,
        )


@dataclass(frozen=True)
class ChildCausal(InvocationDerivationPolicy):
    subject: InvocationSubjectPolicy
    parent: easynet_sdk.ReceiptReference

    def request(
        self,
        *,
        caller_ura: str,
        ability_ura: str,
        resolved_subject_ura: str,
        args: object,
        metadata: Mapping[str, object],
    ) -> easynet_sdk.AbilityTargetRequest:
        _require_subject_policy(self.subject)
        if not isinstance(self.parent, easynet_sdk.ReceiptReference):
            raise InvalidArgument(
                "child invocation requires an SDK ReceiptReference parent",
                reason="invalid_parent_receipt_reference",
            )
        return _request(
            caller_ura=caller_ura,
            ability_ura=ability_ura,
            subject_ura=self.subject.select(resolved_subject_ura),
            nonce_base64=easynet_sdk.new_invocation_nonce_base64(),
            causal_context=self.parent.causal_context(),
            args=args,
            metadata=metadata,
        )


@dataclass(frozen=True)
class FreshContextChild:
    """Issue a fresh child bound to the current invocation's receipt."""

    subject: InvocationSubjectPolicy

    def __post_init__(self) -> None:
        _require_subject_policy(self.subject)

    def bind(self, parent: easynet_sdk.ReceiptReference) -> ChildCausal:
        if not isinstance(parent, easynet_sdk.ReceiptReference):
            raise InvalidArgument(
                "context child invocation requires an SDK ReceiptReference",
                reason="invalid_parent_receipt_reference",
            )
        return ChildCausal(subject=self.subject, parent=parent)


def require_invocation_policy(
    value: object,
    *,
    field: str,
) -> InvocationDerivationPolicy:
    """Validate one explicit product-policy configuration value."""
    if not isinstance(value, InvocationDerivationPolicy):
        raise InvalidArgument(
            f"{field} must be an InvocationDerivationPolicy",
            reason="invalid_invocation_derivation_policy",
        )
    return value


def runtime_root_context(
    *,
    caller_ura: str,
    callee_ura: str,
    subject_ura: str,
) -> easynet_sdk.RuntimeCallContext:
    return easynet_sdk.RuntimeCallContext(
        caller_ura=_subject(caller_ura),
        callee_ura=_subject(callee_ura),
        subject_ura=_subject(subject_ura),
        nonce_base64=easynet_sdk.new_invocation_nonce_base64(),
        causal_context={"form": "none"},
    )


def _request(
    *,
    caller_ura: str,
    ability_ura: str,
    subject_ura: str,
    nonce_base64: str,
    causal_context: Mapping[str, object],
    args: object,
    metadata: Mapping[str, object],
) -> easynet_sdk.AbilityTargetRequest:
    return easynet_sdk.AbilityTargetRequest(
        caller_ura=caller_ura,
        ability_ura=ability_ura,
        subject_ura=_subject(subject_ura),
        nonce_base64=nonce_base64,
        causal_context=dict(causal_context),
        args=args,
        metadata=dict(metadata),
    )


def _subject(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidArgument(
            "invocation subject must not be empty",
            reason="empty_subject",
        )
    return value.strip()


def _require_subject_policy(value: object) -> None:
    if not isinstance(value, InvocationSubjectPolicy):
        raise InvalidArgument(
            "an explicit InvocationSubjectPolicy is required",
            reason="invalid_invocation_subject_policy",
        )
