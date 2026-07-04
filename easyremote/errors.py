"""Error taxonomy for EasyRemote.

The seven runtime error kinds mirror the daemon SDK invocation taxonomy
one-to-one; :class:`SchemaError` is the single registration-time error.
Every failure surfaced by this package is an instance of exactly one of
these eight classes. SDK errors, daemon rejections, and transport failures
are folded into the same types so callers never branch on more than one
vocabulary.
"""

from __future__ import annotations

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
]


class RemoteError(Exception):
    """Base class for every runtime error raised by EasyRemote.

    Attributes:
        kind: One of the seven daemon SDK taxonomy kinds (class-fixed).
        reason: Stable, machine-readable identifier for the specific
            failure (e.g. ``"daemon_down"``), suitable for branching.
        invocation_id: The invocation this error belongs to, when known.
        retry_after: Server-suggested backoff in seconds, when provided.
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


_SDK_ERROR_MAP: dict[easynet_sdk.ErrorCode, tuple[type[RemoteError], str]] = {
    easynet_sdk.ErrorCode.INVALID_ARGUMENT: (InvalidArgument, "invalid_argument"),
    easynet_sdk.ErrorCode.INVALID_UTF8: (InvalidArgument, "invalid_utf8"),
    easynet_sdk.ErrorCode.INVALID_INVOCATION: (InvalidArgument, "invalid_invocation"),
    easynet_sdk.ErrorCode.NOT_FOUND: (InvalidArgument, "not_found"),
    easynet_sdk.ErrorCode.ABILITY_NOT_FOUND: (InvalidArgument, "ability_not_found"),
    easynet_sdk.ErrorCode.PERMISSION_DENIED: (PermissionDenied, "permission_denied"),
    easynet_sdk.ErrorCode.ADMISSION_DENIED: (PermissionDenied, "admission_denied"),
    easynet_sdk.ErrorCode.TIMEOUT: (DeadlineExceeded, "timeout"),
    easynet_sdk.ErrorCode.CANCELLED: (Cancelled, "cancelled"),
    easynet_sdk.ErrorCode.DAEMON_OFFLINE: (Unavailable, "daemon_down"),
    easynet_sdk.ErrorCode.NOT_INITIALIZED: (Unavailable, "not_initialized"),
    easynet_sdk.ErrorCode.VERSION_MISMATCH: (Unavailable, "version_mismatch"),
    easynet_sdk.ErrorCode.VERSION_INCOMPATIBLE: (
        Unavailable,
        "version_incompatible",
    ),
    easynet_sdk.ErrorCode.ROUTE_UNAVAILABLE: (Unavailable, "route_unavailable"),
    easynet_sdk.ErrorCode.CONTROL_ONLY: (Unavailable, "control_only"),
    easynet_sdk.ErrorCode.TRANSPORT: (Unavailable, "transport"),
    easynet_sdk.ErrorCode.NULL_POINTER: (InternalError, "null_pointer"),
    easynet_sdk.ErrorCode.INVALID_HANDLE: (InternalError, "invalid_handle"),
    easynet_sdk.ErrorCode.ALREADY_INIT: (InternalError, "already_initialized"),
    easynet_sdk.ErrorCode.PROTOCOL_MISMATCH: (InternalError, "protocol_mismatch"),
    easynet_sdk.ErrorCode.PROTOCOL: (InternalError, "protocol"),
    easynet_sdk.ErrorCode.ABILITY_FAILED: (InternalError, "ability_failed"),
    easynet_sdk.ErrorCode.NOT_IMPLEMENTED: (InternalError, "not_implemented"),
    easynet_sdk.ErrorCode.GENERIC: (InternalError, "generic"),
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
    cls, reason = _SDK_ERROR_MAP.get(
        error.code, (InternalError, error.code.value.lower())
    )
    return cls(
        error.message or _SDK_HINTS.get(reason, reason),
        reason=reason,
        invocation_id=error.invocation_id,
        retry_after=_retry_after(error.details),
    )


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
