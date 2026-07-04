"""Receipt objects and invocation states (SPEC §5.7).

EasyRemote keeps the public receipt API and error taxonomy here. Receipt
summary parsing, state projection, summary-only verification guardrails, and
hash-chain continuity checks are owned by the EasyNet-Cli SDK Receipt facade.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeAlias

import easynet_sdk

from .errors import InternalError, Unavailable, error_from_sdk

__all__ = ["InvocationState", "Receipt", "ReceiptChain"]

InvocationState: TypeAlias = easynet_sdk.EasyRemoteInvocationState


@dataclass(frozen=True)
class Receipt:
    """One daemon receipt summary.

    ``raw`` preserves the exact wire dict; interpretation is delegated to the
    SDK so this package does not duplicate Axon/daemon receipt semantics.
    """

    index: int
    invocation_id: str
    receipt_type: str
    state: InvocationState
    timestamp_unix_ms: int
    prev_receipt_hash: bytes
    self_hash: bytes
    payload_content_type: str
    cleanup_complete: bool
    reason: str
    child_invocation_id: str
    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_wire(cls, wire: dict[str, Any]) -> Receipt:
        try:
            return cls._from_sdk(easynet_sdk.EasyRemoteReceipt.from_wire(wire))
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def verify(self, resolver: object | None = None) -> None:
        """Cryptographically verify this receipt when the daemon supplies it.

        Local invoke responses still contain summary-only receipts. The SDK
        reports that gap explicitly; EasyRemote maps it to its public
        ``Unavailable`` error for compatibility.
        """

        try:
            self._to_sdk().verify()
        except easynet_sdk.SDKError as exc:
            if exc.details.get("reason") == "full_receipt_unavailable":
                raise Unavailable(
                    exc.message,
                    reason="full_receipt_unavailable",
                    invocation_id=exc.invocation_id,
                ) from exc
            raise error_from_sdk(exc) from exc

    @classmethod
    def _from_sdk(cls, receipt: easynet_sdk.EasyRemoteReceipt) -> Receipt:
        return cls(
            index=receipt.index,
            invocation_id=receipt.invocation_id,
            receipt_type=receipt.receipt_type,
            state=receipt.state,
            timestamp_unix_ms=receipt.timestamp_unix_ms,
            prev_receipt_hash=receipt.prev_receipt_hash,
            self_hash=receipt.self_hash,
            payload_content_type=receipt.payload_content_type,
            cleanup_complete=receipt.cleanup_complete,
            reason=receipt.reason,
            child_invocation_id=receipt.child_invocation_id,
            raw=dict(receipt.raw),
        )

    def _to_sdk(self) -> easynet_sdk.EasyRemoteReceipt:
        return easynet_sdk.EasyRemoteReceipt(
            index=self.index,
            invocation_id=self.invocation_id,
            receipt_type=self.receipt_type,
            state=self.state,
            timestamp_unix_ms=self.timestamp_unix_ms,
            prev_receipt_hash=self.prev_receipt_hash,
            self_hash=self.self_hash,
            payload_content_type=self.payload_content_type,
            cleanup_complete=self.cleanup_complete,
            reason=self.reason,
            child_invocation_id=self.child_invocation_id,
            raw=dict(self.raw),
        )


class ReceiptChain(Sequence[Receipt]):
    """An ordered receipt sequence with SDK-owned hash-link checking."""

    def __init__(self, receipts: Sequence[Receipt]) -> None:
        self._receipts = tuple(receipts)

    def __len__(self) -> int:
        return len(self._receipts)

    def __getitem__(self, index: int) -> Receipt:  # type: ignore[override]
        return self._receipts[index]

    def __iter__(self) -> Iterator[Receipt]:
        return iter(self._receipts)

    def verify_continuity(self) -> None:
        try:
            easynet_sdk.EasyRemoteReceiptChain(
                tuple(receipt._to_sdk() for receipt in self._receipts)
            ).verify_continuity()
        except easynet_sdk.SDKError as exc:
            mapped = error_from_sdk(exc)
            if isinstance(mapped, InternalError):
                raise mapped from exc
            raise InternalError(
                str(mapped),
                reason=mapped.reason or "receipt_chain_broken",
                invocation_id=mapped.invocation_id,
            ) from exc
