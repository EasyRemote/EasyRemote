"""Server-side composition context (SPEC §5.5) — type and contract.

:class:`Context` is defined ahead of its dispatch wiring so that
registration can *recognize* Context-taking functions today. Actually
serving them requires the daemon's external-host-attach protocol
(SPEC §9, Cli PR-1): the shell executor delivers call args through
argv templates only — neither ``caller`` nor ``invocation_id``
traverses that path, and fabricating them would corrupt the receipt
chain. Until PR-1 lands, every dispatch surface here fails loudly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import Unavailable

__all__ = ["Context"]

_NOT_WIRED = (
    "Context dispatch requires the daemon external-host-attach protocol"
    " (SPEC §9 PR-1) — the shell executor cannot deliver caller identity"
    " or invocation ids to a warm host"
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
