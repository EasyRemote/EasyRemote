"""Server-side invocation context (SPEC §5.5) — type and contract.

``host_stream`` now lets the daemon inject read-only caller identity and
the runtime invocation id into a warm EasyRemote function. Composition
methods remain deliberately unavailable until the parent-receipt URA
path exists: child calls need a causal reference, not just a caller
string, or the receipt chain becomes unverifiable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import Unavailable

__all__ = ["Context"]

_NOT_WIRED = (
    "Context child dispatch requires the parent receipt URA path"
    " (RFC-007/008) so child invocations can carry a verifiable"
    " causal_context"
)


@dataclass(frozen=True)
class Context:
    """Injected first parameter for composing capabilities server-side.

    ``ctx.call`` creates a child invocation whose causal context is
    automatically chained to the current one — composition as a
    first-class citizen of the receipt chain.
    """

    invocation_id: str
    caller: str

    def call(self, function: str, /, *args: Any, **kwargs: Any) -> Any:
        raise Unavailable(_NOT_WIRED, reason="context_dispatch_not_wired")

    def invoke(self, function: str, /, *args: Any, **kwargs: Any) -> Any:
        raise Unavailable(_NOT_WIRED, reason="context_dispatch_not_wired")

    def stream(self, function: str, /, *args: Any, **kwargs: Any) -> Any:
        raise Unavailable(_NOT_WIRED, reason="context_dispatch_not_wired")

    def progress(self, payload: dict[str, Any] | bytes) -> None:
        raise Unavailable(_NOT_WIRED, reason="context_dispatch_not_wired")

    def recv(self, timeout: float | None = None) -> Any:
        raise Unavailable(_NOT_WIRED, reason="context_dispatch_not_wired")

    @property
    def cancelled(self) -> bool:
        raise Unavailable(_NOT_WIRED, reason="context_dispatch_not_wired")
