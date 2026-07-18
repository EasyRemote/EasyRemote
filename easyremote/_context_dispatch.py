"""SDK-backed child dispatch for server-injected Context objects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import easynet_sdk

from .client import Client, Stream
from .errors import Unavailable
from .invocation import Invocation
from .invocation_policy import ChildCausal, ResolvedTargetSubject
from .receipts import receipt_reference


def dispatcher_from_parent_receipt(
    parent_receipt: easynet_sdk.RuntimeReceipt | None,
    *,
    client_factory: Callable[[], Client] = Client,
) -> SDKContextChildDispatcher | None:
    """Create a child dispatcher only when a parent receipt anchor exists."""

    if parent_receipt is None:
        return None
    parent_reference = _parent_reference(parent_receipt)
    return SDKContextChildDispatcher(
        parent_reference,
        client_factory=client_factory,
    )


@dataclass
class SDKContextChildDispatcher:
    """Context child calls over the normal EasyRemote client path.

    The dispatcher owns only ergonomics and lifetime. The parent receipt is
    projected through the EasyNet-Cli SDK RuntimeReceipt provider before this
    object is created; all child calls still flow through `Client.prepare`,
    preserving the complete seven-tuple before dispatch.
    """

    parent_reference: easynet_sdk.ReceiptReference
    client_factory: Callable[[], Client] = Client
    _client: Client | None = field(default=None, init=False, repr=False)

    def call(self, function: str, /, *args: Any, **kwargs: Any) -> Any:
        return self._client_or_create().call(
            Client.target(function, invocation_policy=self._child_policy()),
            *args,
            **kwargs,
        )

    def invoke(self, function: str, /, *args: Any, **kwargs: Any) -> Invocation:
        return self._client_or_create().invoke(
            Client.target(function, invocation_policy=self._child_policy()),
            *args,
            **kwargs,
        )

    def stream(self, function: str, /, *args: Any, **kwargs: Any) -> Stream:
        return self._client_or_create().stream(
            Client.target(function, invocation_policy=self._child_policy()),
            *args,
            **kwargs,
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _client_or_create(self) -> Client:
        if self._client is None:
            self._client = self.client_factory()
        return self._client

    def _child_policy(self) -> ChildCausal:
        return ChildCausal(
            subject=ResolvedTargetSubject(),
            parent=self.parent_reference,
        )


def _parent_reference(
    receipt: easynet_sdk.RuntimeReceipt,
) -> easynet_sdk.ReceiptReference:
    try:
        return receipt_reference(receipt)
    except easynet_sdk.SDKError as exc:
        raise Unavailable(
            "Context child dispatch requires a parent receipt_ura and"
            " receipt hash returned by the daemon",
            reason="parent_receipt_anchor_unavailable",
        ) from exc
