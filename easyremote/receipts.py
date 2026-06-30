"""Receipt objects and invocation states (SPEC §5.7).

What the daemon returns over C ABI v3 is a *receipt summary* — the
hash-chain fields without the signed axiom binding (source:
``EasyNet-Cli/src/ffi/invocation.rs::receipt_summary_json``). Two
consequences, kept honest here:

- hash-chain continuity IS checkable (:meth:`ReceiptChain.verify_continuity`),
- cryptographic verification (M1/M2/M3) is NOT possible from a summary;
  :meth:`Receipt.verify` says so explicitly until the full-receipt fetch
  path lands (flagged SPEC §6 gap, resolved by P0).

``receipt_type`` stays a raw string label, matching Axon's canonical
receipt body. Older integer summaries are accepted and stringified so
callers do not lose the daemon's original ``raw`` value.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from .errors import InternalError, Unavailable

__all__ = ["InvocationState", "Receipt", "ReceiptChain"]


class InvocationState(IntEnum):
    """Invocation lifecycle states.

    Numbering is normative, from ``axon/v1/types.proto:880``.
    """

    UNSPECIFIED = 0
    ACCEPTED = 1
    ADMITTED = 2
    DISPATCHED = 3
    RUNNING = 4
    COMPLETED = 5
    FAILED = 6
    TIMED_OUT = 7
    CANCELLED = 8

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATES


_TERMINAL_STATES = frozenset(
    {
        InvocationState.COMPLETED,
        InvocationState.FAILED,
        InvocationState.TIMED_OUT,
        InvocationState.CANCELLED,
    }
)

_STATE_NAMES = {
    "unspecified": InvocationState.UNSPECIFIED,
    "accepted": InvocationState.ACCEPTED,
    "admitted": InvocationState.ADMITTED,
    "dispatched": InvocationState.DISPATCHED,
    "running": InvocationState.RUNNING,
    "completed": InvocationState.COMPLETED,
    "failed": InvocationState.FAILED,
    "timed_out": InvocationState.TIMED_OUT,
    "cancelled": InvocationState.CANCELLED,
}


@dataclass(frozen=True)
class Receipt:
    """One receipt summary from the daemon.

    ``raw`` always preserves the exact wire dict, so nothing the daemon
    said is ever lost to this wrapper.
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
            return cls(
                index=int(wire["index"]),
                invocation_id=str(wire["invocation_id"]),
                receipt_type=str(wire["receipt_type"]),
                state=_parse_state(wire["state"]),
                timestamp_unix_ms=int(wire["timestamp_unix_ms"]),
                prev_receipt_hash=bytes.fromhex(wire["prev_receipt_hash_hex"]),
                self_hash=bytes.fromhex(wire["self_hash_hex"]),
                payload_content_type=str(wire.get("payload_content_type", "")),
                cleanup_complete=bool(wire.get("cleanup_complete", False)),
                reason=str(wire.get("reason", "")),
                child_invocation_id=str(wire.get("child_invocation_id", "")),
                raw=wire,
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise InternalError(
                f"daemon receipt summary is malformed: {exc}", reason="protocol"
            ) from exc

    def verify(self, resolver: object | None = None) -> None:
        """Cryptographically verify this receipt — not yet possible.

        C ABI v3 delivers receipt *summaries* without the signed axiom
        binding, so there is nothing here to verify a signature against.
        The full-receipt fetch path is the flagged SPEC §6 gap; until it
        lands, failing loudly beats pretending to verify.
        """
        raise Unavailable(
            "cryptographic receipt verification needs the full receipt body,"
            " which C ABI v3 does not deliver (summaries only) — tracked as"
            " SPEC §6 'receipt body' gap",
            reason="full_receipt_unavailable",
        )


class ReceiptChain(Sequence[Receipt]):
    """An ordered receipt sequence with hash-link checking."""

    def __init__(self, receipts: Sequence[Receipt]) -> None:
        self._receipts = tuple(receipts)

    def __len__(self) -> int:
        return len(self._receipts)

    def __getitem__(self, index: int) -> Receipt:  # type: ignore[override]
        return self._receipts[index]

    def __iter__(self) -> Iterator[Receipt]:
        return iter(self._receipts)

    def verify_continuity(self) -> None:
        """Check the hash links: each receipt must cite its predecessor.

        This is the integrity check a summary *can* support. Raises
        :class:`InternalError` (reason ``receipt_chain_broken``) at the
        first broken link.
        """
        for position in range(1, len(self._receipts)):
            previous, current = self._receipts[position - 1], self._receipts[position]
            if current.prev_receipt_hash != previous.self_hash:
                raise InternalError(
                    f"receipt chain broken at index {current.index}:"
                    " prev_receipt_hash does not match predecessor's self_hash",
                    reason="receipt_chain_broken",
                    invocation_id=current.invocation_id,
                )


def _parse_state(value: Any) -> InvocationState:
    if isinstance(value, str):
        parsed = _STATE_NAMES.get(value.strip().lower())
        if parsed is not None:
            return parsed
    try:
        return InvocationState(int(value))
    except (ValueError, TypeError):
        # A state this package doesn't know yet must not crash receipt
        # parsing — preserve it as UNSPECIFIED; `raw` keeps the number.
        return InvocationState.UNSPECIFIED
