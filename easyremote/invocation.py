"""EasyRemote presentation over canonical SDK Invocation objects.

The EasyNet-Cli SDK owns the complete Invocation tuple, descriptor binding,
wire encoding, signing, admission, lifecycle, and receipt projections.
EasyRemote owns only product result unwrapping and the inspect-before-send
ergonomic used by its client facade.
"""

from __future__ import annotations

import base64
import builtins
import json
from collections.abc import Callable, Mapping
from typing import Any, Literal, TypeAlias

import easynet_sdk

from .errors import InternalError, InvalidArgument

__all__ = [
    "DispatchCarrier",
    "Invocation",
    "PreparedInvocation",
    "StreamSpec",
]

JSON_CONTENT_TYPE = "application/json"

StreamSpec: TypeAlias = easynet_sdk.BidiStreamDescriptor
DispatchCarrier = Literal["stream", "unary"]
Dispatcher = Callable[["PreparedInvocation"], "Invocation"]


class Invocation:
    """Product-facing view of one canonical SDK terminal result."""

    def __init__(
        self,
        result: easynet_sdk.InvocationResult,
        state: easynet_sdk.InvocationLifecycleState,
        raw_response: Mapping[str, object],
    ) -> None:
        if not isinstance(result, easynet_sdk.InvocationResult) or not result.ok:
            raise InternalError(
                "a successful SDK InvocationResult is required",
                reason="protocol",
            )
        if not isinstance(state, easynet_sdk.InvocationLifecycleState):
            raise InternalError(
                "a canonical SDK InvocationLifecycleState is required",
                reason="protocol",
            )
        if not state.is_terminal:
            raise InternalError(
                f"SDK returned non-terminal Invocation state {state.name}",
                reason="protocol",
            )
        self._result = result
        self._state = state
        self._raw_response = dict(raw_response)

    @classmethod
    def from_transport_response(
        cls,
        response: Mapping[str, object],
    ) -> Invocation:
        runtime_result = response.get("sdk_runtime_result")
        if not isinstance(runtime_result, Mapping):
            raise InternalError(
                "SDK transport response is missing sdk_runtime_result",
                reason="protocol",
            )
        try:
            result = easynet_sdk.InvocationResult.from_json(
                json.dumps(runtime_result, separators=(",", ":"), sort_keys=True)
            )
        except easynet_sdk.SDKError as exc:
            raise InternalError(
                f"SDK runtime result projection is malformed: {exc}",
                reason="protocol",
            ) from exc
        return cls(result, result.lifecycle_state, response)

    @property
    def tuple(self) -> easynet_sdk.InvocationDraft:
        return self._result.tuple

    @property
    def id(self) -> str:
        receipt = self.receipt
        return receipt.invocation_id if receipt is not None else ""

    @property
    def state(self) -> easynet_sdk.InvocationLifecycleState:
        return self._state

    def result(self) -> Any:
        """Return the product value while retaining the canonical raw result."""

        if self._result.output_content_type == JSON_CONTENT_TYPE:
            if self._result.output_json is not None:
                return _unwrap_executor_envelope(self._result.output_json)
            data = self._decoded_result_bytes()
            return _unwrap_executor_envelope(json.loads(data)) if data else None
        return self._decoded_result_bytes()

    @property
    def receipt(self) -> easynet_sdk.RuntimeReceipt | None:
        """Return the strongest receipt fact supplied by the SDK."""

        return (
            self._result.terminal_receipt_summary
            or self._result.admission_receipt_summary
        )

    def receipts(self) -> builtins.tuple[easynet_sdk.RuntimeReceipt, ...]:
        ordered = (
            self._result.admission_receipt_summary,
            self._result.terminal_receipt_summary,
        )
        return builtins.tuple(receipt for receipt in ordered if receipt is not None)

    @property
    def elapsed_ms(self) -> int:
        return self._result.elapsed_ms

    @property
    def raw_response(self) -> dict[str, object]:
        return dict(self._raw_response)

    @property
    def sdk_result(self) -> easynet_sdk.InvocationResult:
        return self._result

    def _decoded_result_bytes(self) -> bytes:
        encoded = self._result.output_base64
        return base64.b64decode(encoded, validate=True) if encoded else b""


class PreparedInvocation:
    """Inspect-before-send handle over one canonical SDK draft."""

    __slots__ = (
        "_call_carrier",
        "_dispatcher",
        "_draft",
        "_sign",
    )

    def __init__(
        self,
        *,
        draft: easynet_sdk.InvocationDraft,
        sign: bool | None = None,
        call_carrier: DispatchCarrier = "unary",
        dispatcher: Dispatcher,
    ) -> None:
        if not isinstance(draft, easynet_sdk.InvocationDraft):
            raise InvalidArgument(
                "SDK InvocationDraft is required",
                reason="invalid_invocation_draft",
            )
        self._draft = draft
        self._sign = sign
        self._call_carrier = call_carrier
        self._dispatcher = dispatcher

    @property
    def draft(self) -> easynet_sdk.InvocationDraft:
        return self._draft

    @property
    def tuple(self) -> easynet_sdk.InvocationDraft:
        return self._draft

    @property
    def metadata(self) -> Mapping[str, str] | None:
        return self._draft.metadata

    @property
    def sign(self) -> bool | None:
        return self._sign

    @property
    def call_carrier(self) -> DispatchCarrier:
        return self._call_carrier

    def send(self) -> Invocation:
        return self._dispatcher(self)


def _unwrap_executor_envelope(value: Any) -> Any:
    """Expose EasyRemote function results instead of product routing envelopes."""

    if (
        isinstance(value, dict)
        and "fulfilled_by" in value
        and "exit_code" in value
        and isinstance(value.get("result"), str)
    ):
        try:
            return json.loads(value["result"])
        except json.JSONDecodeError:
            return value["result"]
    if isinstance(value, dict) and "fulfilled_by" in value and "result" in value:
        return value["result"]
    return value
