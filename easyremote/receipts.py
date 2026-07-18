"""Versioned public receipt shapes over canonical SDK receipt facts."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeAlias, overload

import easynet_sdk

from .errors import InternalError, Unavailable

__all__ = [
    "InvocationState",
    "Receipt",
    "ReceiptChain",
    "receipt_from_mapping",
    "receipt_reference",
]

InvocationState: TypeAlias = easynet_sdk.InvocationLifecycleState


@dataclass(frozen=True)
class Receipt:
    """Released presentation shape backed by one SDK RuntimeReceipt."""

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
    _runtime_receipt: easynet_sdk.RuntimeReceipt = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        canonical, lifecycle_state = _decode_released_receipt(self.raw)
        projected = _receipt_projection(canonical, lifecycle_state)
        supplied = (
            self.index,
            self.invocation_id,
            self.receipt_type,
            self.state,
            self.timestamp_unix_ms,
            self.prev_receipt_hash,
            self.self_hash,
            self.payload_content_type,
            self.cleanup_complete,
            self.reason,
            self.child_invocation_id,
        )
        if supplied != projected:
            raise InternalError(
                "released Receipt fields do not match the SDK receipt projection",
                reason="receipt_protocol",
                invocation_id=canonical.invocation_id,
            )
        object.__setattr__(self, "raw", canonical.to_json_dict())
        object.__setattr__(self, "_runtime_receipt", canonical)

    @classmethod
    def from_wire(cls, wire: Mapping[str, object]) -> Receipt:
        canonical, lifecycle_state = _decode_released_receipt(wire)
        return cls(
            *_receipt_projection(canonical, lifecycle_state),
            raw=canonical.to_json_dict(),
        )

    def verify(self, resolver: object | None = None) -> None:
        del resolver
        raise Unavailable(
            "RuntimeReceipt summaries are non-verifying; use "
            "easynet_sdk.ReceiptClient with a full InvocationReceipt",
            reason="full_receipt_unavailable",
            invocation_id=self.invocation_id,
        )

    def reference(self) -> easynet_sdk.ReceiptReference:
        try:
            return easynet_sdk.ReceiptReference.from_runtime_receipt(
                self._runtime_receipt,
            )
        except easynet_sdk.SDKError as exc:
            raise Unavailable(
                "receipt summary does not include a canonical causal anchor",
                reason="parent_receipt_anchor_unavailable",
                invocation_id=self.invocation_id,
            ) from exc


class ReceiptChain(Sequence[Receipt]):
    """Released ordered container; chain verification remains SDK-owned."""

    def __init__(self, receipts: Sequence[Receipt]) -> None:
        self._receipts = tuple(receipts)

    def __len__(self) -> int:
        return len(self._receipts)

    @overload
    def __getitem__(self, index: int) -> Receipt: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[Receipt, ...]: ...

    def __getitem__(self, index: int | slice) -> Receipt | tuple[Receipt, ...]:
        return self._receipts[index]

    def __iter__(self) -> Iterator[Receipt]:
        return iter(self._receipts)

    def verify_continuity(self) -> None:
        raise Unavailable(
            "RuntimeReceipt summaries cannot be chain-verified; use "
            "easynet_sdk.ReceiptClient.verify_chain with full InvocationReceipt values",
            reason="full_receipt_chain_unavailable",
        )


def receipt_from_mapping(
    value: Mapping[str, object],
) -> easynet_sdk.RuntimeReceipt:
    """Decode internal runtime input directly into the canonical SDK model."""

    return _decode_runtime_receipt(value)[0]


def receipt_reference(
    receipt: easynet_sdk.RuntimeReceipt,
) -> easynet_sdk.ReceiptReference:
    """Project an internal canonical receipt into canonical scalar causality."""

    return easynet_sdk.ReceiptReference.from_runtime_receipt(receipt)


def _receipt_projection(
    receipt: easynet_sdk.RuntimeReceipt,
    lifecycle_state: InvocationState,
) -> tuple[
    int,
    str,
    str,
    InvocationState,
    int,
    bytes,
    bytes,
    str,
    bool,
    str,
    str,
]:
    payload_content_type = receipt.raw.get("payload_content_type", "")
    return (
        receipt.index,
        receipt.invocation_id,
        receipt.receipt_type,
        lifecycle_state,
        receipt.timestamp_unix_ms,
        receipt.prev_receipt_hash(),
        receipt.self_receipt_hash(),
        payload_content_type if isinstance(payload_content_type, str) else "",
        bool(receipt.cleanup_complete),
        receipt.reason,
        receipt.child_invocation_id,
    )


def _decode_runtime_receipt(
    value: Mapping[str, object],
) -> tuple[easynet_sdk.RuntimeReceipt, InvocationState]:
    receipt = easynet_sdk.RuntimeReceipt.from_required_mapping(value)
    try:
        lifecycle_state = easynet_sdk.InvocationLifecycleState[receipt.state.upper()]
    except KeyError as exc:
        raise easynet_sdk.SDKError(
            code=easynet_sdk.ErrorCode.INVALID_ARGUMENT,
            stage="decode",
            retry=easynet_sdk.RetryHint.NEVER,
            message=f"runtime receipt has unknown lifecycle state: {receipt.state!r}",
            invocation_id=receipt.invocation_id,
            details={"reason": "invalid_lifecycle_state"},
            cause=exc,
        ) from exc
    return receipt, lifecycle_state


def _decode_released_receipt(
    value: Mapping[str, object],
) -> tuple[easynet_sdk.RuntimeReceipt, InvocationState]:
    try:
        return _decode_runtime_receipt(value)
    except easynet_sdk.SDKError as exc:
        raise InternalError(
            f"daemon receipt summary is malformed: {exc}",
            reason="receipt_protocol",
            invocation_id=exc.invocation_id,
        ) from exc
