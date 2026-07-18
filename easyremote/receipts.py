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
        try:
            canonical = easynet_sdk.RuntimeReceipt.from_required_mapping(self.raw)
        except easynet_sdk.SDKError as exc:
            raise InternalError(
                f"daemon receipt summary is malformed: {exc}",
                reason="receipt_protocol",
            ) from exc
        projected = _receipt_projection(canonical)
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
        try:
            canonical = easynet_sdk.RuntimeReceipt.from_required_mapping(wire)
        except easynet_sdk.SDKError as exc:
            raise InternalError(
                f"daemon receipt summary is malformed: {exc}",
                reason="receipt_protocol",
            ) from exc
        return cls(*_receipt_projection(canonical), raw=canonical.to_json_dict())

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

    return easynet_sdk.RuntimeReceipt.from_required_mapping(value)


def receipt_reference(
    receipt: easynet_sdk.RuntimeReceipt,
) -> easynet_sdk.ReceiptReference:
    """Project an internal canonical receipt into canonical scalar causality."""

    return easynet_sdk.ReceiptReference.from_runtime_receipt(receipt)


def _receipt_projection(
    receipt: easynet_sdk.RuntimeReceipt,
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
        _lifecycle_state(receipt.state),
        receipt.timestamp_unix_ms,
        receipt.prev_receipt_hash(),
        receipt.self_receipt_hash(),
        payload_content_type if isinstance(payload_content_type, str) else "",
        bool(receipt.cleanup_complete),
        receipt.reason,
        receipt.child_invocation_id,
    )


def _lifecycle_state(value: str) -> InvocationState:
    normalized = value.replace("_", "").replace("-", "").lower()
    for state in InvocationState:
        if state.name.replace("_", "").lower() == normalized:
            return state
    try:
        return InvocationState(int(value))
    except (TypeError, ValueError):
        return InvocationState.UNSPECIFIED
