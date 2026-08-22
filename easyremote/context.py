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

from .errors import InvalidArgument, Unavailable
from .invocation_policy import FreshContextChild

__all__ = ["Context", "ContextTarget"]

_NOT_WIRED = (
    "Context child dispatch requires a daemon/Axon parent receipt anchor"
    " so child invocations can carry a verifiable causal_context"
)


@dataclass(frozen=True)
class ContextTarget:
    """A child target with an explicit parent-bound derivation policy."""

    function: str
    invocation_policy: FreshContextChild

    def __post_init__(self) -> None:
        if not isinstance(self.function, str) or not self.function.strip():
            raise InvalidArgument(
                "context target function must not be empty",
                reason="empty_function",
            )
        if not isinstance(self.invocation_policy, FreshContextChild):
            raise InvalidArgument(
                "context target requires a FreshContextChild policy",
                reason="invalid_invocation_derivation_policy",
            )


class ContextChildDispatcher(Protocol):
    """Child-call behavior supplied by the host integration layer."""

    def call(self, target: ContextTarget, /, *args: Any, **kwargs: Any) -> Any: ...

    def invoke(self, target: ContextTarget, /, *args: Any, **kwargs: Any) -> Any: ...

    def stream(self, target: ContextTarget, /, *args: Any, **kwargs: Any) -> Any: ...

    def close(self) -> None: ...


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

    @staticmethod
    def target(
        function: str,
        /,
        *,
        invocation_policy: FreshContextChild,
    ) -> ContextTarget:
        """Declare child tuple derivation before entering a context dispatch."""
        return ContextTarget(
            function=function,
            invocation_policy=invocation_policy,
        )

    def call(self, target: ContextTarget, /, *args: Any, **kwargs: Any) -> Any:
        explicit_target = self._explicit_target(target)
        return self._dispatcher().call(
            explicit_target,
            *args,
            **kwargs,
        )

    def invoke(self, target: ContextTarget, /, *args: Any, **kwargs: Any) -> Any:
        explicit_target = self._explicit_target(target)
        return self._dispatcher().invoke(
            explicit_target,
            *args,
            **kwargs,
        )

    def stream(self, target: ContextTarget, /, *args: Any, **kwargs: Any) -> Any:
        explicit_target = self._explicit_target(target)
        return self._dispatcher().stream(
            explicit_target,
            *args,
            **kwargs,
        )

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

    @staticmethod
    def _explicit_target(value: object) -> ContextTarget:
        if not isinstance(value, ContextTarget):
            raise InvalidArgument(
                "Context child dispatch requires Context.target(...) with an"
                " explicit FreshContextChild policy",
                reason="missing_invocation_derivation_policy",
            )
        return value
