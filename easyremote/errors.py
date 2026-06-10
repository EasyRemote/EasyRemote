"""Error taxonomy for EasyRemote.

The seven runtime error kinds mirror the Axon invocation error taxonomy
one-to-one (SPEC §5.8); :class:`SchemaError` is the single
registration-time error. Every failure surfaced by this package is an
instance of exactly one of these eight classes — C ABI codes, daemon
rejections, and transport failures are all folded into the same types,
so callers never branch on more than one vocabulary.
"""

from __future__ import annotations

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
    "error_from_abi",
]


class RemoteError(Exception):
    """Base class for every runtime error raised by EasyRemote.

    Attributes:
        kind: One of the seven Axon taxonomy kinds (class-fixed).
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

        Mirrors the Axon SDK contract: UNAVAILABLE is always retriable;
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


# libeasynet_cli error codes (include/easynet_cli.h, ABI v3) → taxonomy.
# Codes 2/4/6 indicate binding bugs, not user errors; they still map to
# INTERNAL so callers see one vocabulary, with `reason` preserving the
# precise cause.
_ABI_ERRORS: dict[int, tuple[type[RemoteError], str]] = {
    1: (InternalError, "generic"),
    2: (InternalError, "null_pointer"),
    3: (InvalidArgument, "invalid_utf8"),
    4: (InternalError, "invalid_handle"),
    5: (Unavailable, "not_initialized"),
    6: (InternalError, "already_initialized"),
    7: (Unavailable, "daemon_down"),
    8: (Unavailable, "version_incompatible"),
    9: (InternalError, "ability_failed"),
    10: (InternalError, "not_implemented"),
    11: (InvalidArgument, "invalid_argument"),
    12: (PermissionDenied, "permission_denied"),
    13: (InvalidArgument, "not_found"),
    14: (Cancelled, "cancelled"),
    15: (InternalError, "protocol"),
    16: (DeadlineExceeded, "timeout"),
}

_ABI_HINTS: dict[str, str] = {
    "daemon_down": "easynet-daemon is not reachable — start it with `easynet start`",
    "not_initialized": "transport not connected — connect a Transport first",
    "version_incompatible": "libeasynet_cli and easynet-daemon disagree on versions"
    " — update both to matching releases",
}


def error_from_abi(code: int, message: str = "") -> RemoteError:
    """Map a libeasynet_cli return code to the taxonomy.

    ``message`` should be the daemon-provided ``easynet_last_error()``
    text; when it is empty, a reason-specific hint is used so the user
    always gets an actionable error.
    """
    cls, reason = _ABI_ERRORS.get(code, (InternalError, f"unknown_abi_code_{code}"))
    return cls(message or _ABI_HINTS.get(reason, reason), reason=reason)
