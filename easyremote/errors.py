"""Error taxonomy for EasyRemote.

The seven runtime error kinds mirror the daemon SDK invocation taxonomy
one-to-one; :class:`SchemaError` is the single registration-time error.
Every failure surfaced by this package is an instance of exactly one of
these eight classes. SDK errors, daemon rejections, and transport failures
are folded into the same types so callers never branch on more than one
vocabulary.
"""

from __future__ import annotations

from collections.abc import Mapping

import easynet_sdk

__all__ = [
    "Cancelled",
    "DeadlineExceeded",
    "InternalError",
    "InvalidArgument",
    "PermissionDenied",
    "RemoteError",
    "ResourceExhausted",
    "SchemaError",
    "Unavailable",
    "error_from_sdk",
    "error_from_wire",
    "is_runtime_offline_error",
]


class RemoteError(Exception):
    """Base class for every runtime error raised by EasyRemote.

    Attributes:
        kind: One of the seven daemon SDK taxonomy kinds (class-fixed).
        reason: Stable, machine-readable identifier for the specific
            failure (e.g. ``"daemon_down"``), suitable for branching.
        invocation_id: The invocation this error belongs to, when known.
        retry_after: Server-suggested backoff in seconds, when provided.
        trace: Native Axon invocation graph, when a product facade could read
            it after the failure.
        trace_lookup_error: Why post-failure trace lookup was unavailable. This
            never replaces the original invocation error.
    """

    KIND = "INTERNAL"

    def __init__(
        self,
        message: str = "",
        *,
        reason: str = "",
        invocation_id: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message or reason or self.KIND)
        self.reason = reason
        self.invocation_id = invocation_id
        self.retry_after = retry_after
        self.trace: Mapping[str, object] | None = None
        self.trace_lookup_error: str | None = None

    @property
    def kind(self) -> str:
        return self.KIND

    @property
    def retriable(self) -> bool:
        """Whether a caller may safely retry this invocation.

        Mirrors the daemon SDK contract: UNAVAILABLE is always retriable;
        RESOURCE_EXHAUSTED only when the server suggested a backoff.
        """
        if self.KIND == Unavailable.KIND:
            return True
        return self.KIND == ResourceExhausted.KIND and self.retry_after is not None


class Cancelled(RemoteError):
    KIND = "CANCELLED"


class DeadlineExceeded(RemoteError):
    KIND = "DEADLINE_EXCEEDED"


class Unavailable(RemoteError):
    KIND = "UNAVAILABLE"


class InvalidArgument(RemoteError):
    KIND = "INVALID_ARGUMENT"


class ResourceExhausted(RemoteError):
    KIND = "RESOURCE_EXHAUSTED"


class PermissionDenied(RemoteError):
    KIND = "PERMISSION_DENIED"


class InternalError(RemoteError):
    KIND = "INTERNAL"


class SchemaError(ValueError):
    """A registered function's signature cannot become an ability schema.

    Raised at registration time, never at call time.
    """


_SDK_ERROR_CLASS_MAP: dict[easynet_sdk.ErrorClass, type[RemoteError]] = {
    easynet_sdk.ErrorClass.VALIDATION: InvalidArgument,
    easynet_sdk.ErrorClass.HANDLE: InternalError,
    easynet_sdk.ErrorClass.LIFECYCLE: Unavailable,
    easynet_sdk.ErrorClass.AVAILABILITY: Unavailable,
    easynet_sdk.ErrorClass.PERMISSION: PermissionDenied,
    easynet_sdk.ErrorClass.ADMISSION: PermissionDenied,
    easynet_sdk.ErrorClass.ROUTING: InvalidArgument,
    easynet_sdk.ErrorClass.TIMEOUT: DeadlineExceeded,
    easynet_sdk.ErrorClass.CANCELLATION: Cancelled,
    easynet_sdk.ErrorClass.PROTOCOL: InternalError,
    easynet_sdk.ErrorClass.VERSION: Unavailable,
    easynet_sdk.ErrorClass.CONTROL: Unavailable,
    easynet_sdk.ErrorClass.UNSUPPORTED: InternalError,
    easynet_sdk.ErrorClass.GENERIC: InternalError,
}

# Product taxonomy intentionally distinguishes lifecycle/setup defects and
# execution failures from denial decisions, even where the generic SDK class
# groups them together. All other codes inherit their public class from the
# canonical SDK classification, so SDK additions cannot silently fall back to
# an unrelated product error class.
_SDK_ERROR_OVERRIDES: dict[easynet_sdk.ErrorCode, type[RemoteError]] = {
    easynet_sdk.ErrorCode.ALREADY_INIT: InternalError,
    easynet_sdk.ErrorCode.NULL_POINTER: InternalError,
    easynet_sdk.ErrorCode.RUNTIME_OFFLINE: Unavailable,
    easynet_sdk.ErrorCode.CALLER_IDENTITY_UNAVAILABLE: Unavailable,
    easynet_sdk.ErrorCode.CALLER_SIGNER_UNAVAILABLE: Unavailable,
    easynet_sdk.ErrorCode.ROUTE_UNAVAILABLE: Unavailable,
    easynet_sdk.ErrorCode.DESCRIPTOR_OWNER_OFFLINE: Unavailable,
    easynet_sdk.ErrorCode.DESCRIPTOR_STALE: Unavailable,
    easynet_sdk.ErrorCode.RUNTIME_ROUTE_UNAVAILABLE: Unavailable,
    easynet_sdk.ErrorCode.EXECUTION_FAILED: InternalError,
    easynet_sdk.ErrorCode.ABILITY_FAILED: InternalError,
    easynet_sdk.ErrorCode.TERMINAL_RECEIPT_UNAVAILABLE: Unavailable,
    easynet_sdk.ErrorCode.PROVIDER_UNAVAILABLE: Unavailable,
}

_SDK_REASON_OVERRIDES: dict[easynet_sdk.ErrorCode, str] = {
    easynet_sdk.ErrorCode.ALREADY_INIT: "already_initialized",
    easynet_sdk.ErrorCode.RUNTIME_OFFLINE: "daemon_down",
}

_SDK_HINTS: dict[str, str] = {
    "daemon_down": "easynet-daemon is not reachable - start it with `easynet start`",
    "not_initialized": "transport not connected - connect a Transport first",
    "version_incompatible": "easynet-sdk and easynet-daemon disagree on versions"
    " - update both to matching releases",
}


def error_from_sdk(error: easynet_sdk.SDKError) -> RemoteError:
    """Project a typed daemon SDK error into EasyRemote's public taxonomy."""

    if isinstance(error.cause, RemoteError):
        return error.cause
    detail_reason = error.details.get("reason")
    if detail_reason == "signing_path_pending":
        return Unavailable(
            error.message or "caller signing path is not configured",
            reason="signing_path_pending",
            invocation_id=error.invocation_id,
            retry_after=_retry_after(error.details),
        )
    canonical_code = (
        error.code if isinstance(error.code, easynet_sdk.ErrorCode) else None
    )
    cls = (
        _SDK_ERROR_OVERRIDES.get(
            canonical_code,
            _SDK_ERROR_CLASS_MAP[error.error_class],
        )
        if canonical_code is not None
        else _SDK_ERROR_CLASS_MAP[error.error_class]
    )
    reason = (
        _SDK_REASON_OVERRIDES.get(canonical_code, canonical_code.value.lower())
        if canonical_code is not None
        else error.code.lower()
    )
    if isinstance(detail_reason, str) and detail_reason:
        reason = detail_reason
    return cls(
        error.message or _SDK_HINTS.get(reason, reason),
        reason=reason,
        invocation_id=error.invocation_id,
        retry_after=_retry_after(error.details),
    )


def is_runtime_offline_error(error: easynet_sdk.SDKError) -> bool:
    """Whether a canonical SDK error means the local runtime is unreachable."""

    return bool(error.code == easynet_sdk.ErrorCode.RUNTIME_OFFLINE)


# Every concrete taxonomy class keyed by its wire `KIND` string, so a
# `{kind, reason, message}` error frame round-trips back to the right
# exception type (a stream's terminal error, a receipt failure, …).
# SchemaError is excluded: it subclasses ValueError (registration-time),
# not RemoteError, so it has no wire KIND and never appears in a frame.
_KIND_TO_CLASS: dict[str, type[RemoteError]] = {
    cls.KIND: cls
    for cls in (
        Cancelled,
        DeadlineExceeded,
        Unavailable,
        InvalidArgument,
        ResourceExhausted,
        PermissionDenied,
        InternalError,
    )
}


def error_from_wire(error: dict[str, object]) -> RemoteError:
    """Reconstruct a :class:`RemoteError` from a wire error object.

    Accepts the daemon's ``{kind, reason, message}`` shape (any field may
    be absent). An unknown or missing ``kind`` falls back to
    :class:`InternalError` so the failure still surfaces as one
    vocabulary rather than being swallowed.
    """
    kind = str(error.get("kind") or "")
    reason = str(error.get("reason") or "")
    message = str(error.get("message") or "")
    cls = _KIND_TO_CLASS.get(kind, InternalError)
    return cls(message or reason or kind or "remote stream error", reason=reason)


def _retry_after(details: object) -> float | None:
    if not isinstance(details, dict):
        return None
    value = details.get("retry_after")
    if isinstance(value, int | float) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None
