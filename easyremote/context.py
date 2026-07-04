"""Server-side invocation context (SPEC §5.5) — type and contract.

``host_stream`` lets the daemon inject read-only caller identity, the
runtime invocation id, and, when available, a parent receipt anchor into
a warm EasyRemote function. Composition methods delegate to a child
dispatcher only when that anchor has been projected through the
EasyNet-Cli SDK Receipt profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .errors import Unavailable

__all__ = ["Context"]

_NOT_WIRED = (
    "Context child dispatch requires a daemon/Axon parent receipt anchor"
    " so child invocations can carry a verifiable causal_context"
)


class ContextChildDispatcher(Protocol):
    """Child-call behavior supplied by the host integration layer."""

    def call(self, function: str, /, *args: Any, **kwargs: Any) -> Any:
        ...

    def invoke(self, function: str, /, *args: Any, **kwargs: Any) -> Any:
        ...

    def stream(self, function: str, /, *args: Any, **kwargs: Any) -> Any:
        ...

    def close(self) -> None:
        ...


@dataclass(frozen=True)
class Context:
    """Injected first parameter for server-side caller context.

    This carries read-only identity (`invocation_id`, `caller`). Child
    dispatch methods are available only when the daemon supplied a parent
    receipt anchor that the SDK Receipt profile can turn into a child
    causal context.
    """

    invocation_id: str
    caller: str
    _child_dispatcher: ContextChildDispatcher | None = None

    def call(self, function: str, /, *args: Any, **kwargs: Any) -> Any:
        return self._dispatcher().call(function, *args, **kwargs)

    def invoke(self, function: str, /, *args: Any, **kwargs: Any) -> Any:
        return self._dispatcher().invoke(function, *args, **kwargs)

    def stream(self, function: str, /, *args: Any, **kwargs: Any) -> Any:
        return self._dispatcher().stream(function, *args, **kwargs)

    def progress(self, payload: dict[str, Any] | bytes) -> None:
        raise Unavailable(_NOT_WIRED, reason="context_dispatch_not_wired")

    def recv(self, timeout: float | None = None) -> Any:
        raise Unavailable(_NOT_WIRED, reason="context_dispatch_not_wired")

    @property
    def cancelled(self) -> bool:
        raise Unavailable(_NOT_WIRED, reason="context_dispatch_not_wired")

    def close(self) -> None:
        if self._child_dispatcher is not None:
            self._child_dispatcher.close()

    def _dispatcher(self) -> ContextChildDispatcher:
        if self._child_dispatcher is None:
            raise Unavailable(_NOT_WIRED, reason="context_dispatch_not_wired")
        return self._child_dispatcher
