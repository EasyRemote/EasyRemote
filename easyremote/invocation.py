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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal, TypeAlias, overload

import easynet_sdk

from .errors import InternalError, InvalidArgument

__all__ = [
    "Arguments",
    "CausalRef",
    "DispatchCarrier",
    "Invocation",
    "InvocationTuple",
    "MerkleAnchor",
    "PreparedInvocation",
    "StreamSpec",
]

JSON_CONTENT_TYPE = "application/json"

StreamSpec: TypeAlias = easynet_sdk.BidiStreamDescriptor
DispatchCarrier = Literal["stream", "unary"]
Dispatcher = Callable[["PreparedInvocation"], "Invocation"]
_UNSET = object()


@dataclass(frozen=True)
class Arguments:
    """Released argument shape consumed only by the SDK object adapter."""

    content_type: str
    json_value: Any = None
    raw: bytes | None = None

    @classmethod
    def from_json(cls, value: Any) -> Arguments:
        return cls(content_type=JSON_CONTENT_TYPE, json_value=value)

    @classmethod
    def from_bytes(cls, data: bytes, content_type: str) -> Arguments:
        return cls(content_type=content_type, raw=data)

    @property
    def is_json(self) -> bool:
        return self.raw is None


@dataclass(frozen=True)
class CausalRef:
    """Released scalar causal shape backed by an SDK ReceiptReference."""

    receipt_hash: bytes
    receipt_ura: str
    _reference: easynet_sdk.ReceiptReference = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        try:
            reference = easynet_sdk.ReceiptReference(
                receipt_ura=self.receipt_ura,
                receipt_hash=self.receipt_hash,
            )
        except easynet_sdk.SDKError as exc:
            raise InvalidArgument(
                f"invalid receipt reference: {exc}",
                reason="invalid_receipt_reference",
            ) from exc
        object.__setattr__(self, "receipt_ura", reference.receipt_ura)
        object.__setattr__(self, "_reference", reference)

    @classmethod
    def from_sdk_reference(
        cls,
        reference: easynet_sdk.ReceiptReference,
    ) -> CausalRef:
        if not isinstance(reference, easynet_sdk.ReceiptReference):
            raise InvalidArgument(
                "SDK ReceiptReference is required",
                reason="invalid_receipt_reference",
            )
        return cls(
            receipt_hash=reference.receipt_hash,
            receipt_ura=reference.receipt_ura,
        )

    def to_wire(self) -> dict[str, object]:
        projected = dict(self._reference.causal_context())
        projected.pop("form", None)
        return projected


@dataclass(frozen=True)
class MerkleAnchor:
    """Released Merkle causal shape interpreted by the SDK object adapter."""

    root: bytes
    proof_ura: str


LegacyCausal: TypeAlias = (
    CausalRef
    | easynet_sdk.ReceiptReference
    | Sequence[CausalRef | easynet_sdk.ReceiptReference]
    | MerkleAnchor
    | Mapping[str, object]
    | None
)


@dataclass(frozen=True)
class InvocationTuple:
    """Released seven-field view over one SDK-owned InvocationDraft."""

    caller: str
    callee: str
    ability: str
    subject: str
    nonce: bytes
    causal: LegacyCausal
    arguments: Arguments | Mapping[str, object]
    _draft: easynet_sdk.InvocationDraft = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "_draft", _draft_from_legacy_tuple(self))

    @property
    def sdk_draft(self) -> easynet_sdk.InvocationDraft:
        return self._draft


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
        state_code = response.get("state")
        if not isinstance(state_code, int) or isinstance(state_code, bool):
            raise InternalError(
                "SDK transport response has no recognized canonical terminal state",
                reason="protocol",
            )
        try:
            state = easynet_sdk.InvocationLifecycleState(state_code)
        except ValueError as exc:
            raise InternalError(
                "SDK transport response has no recognized canonical terminal state",
                reason="protocol",
            ) from exc
        return cls(result, state, response)

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
    def selected_node_id(self) -> str:
        return self._result.selected_node_id

    @property
    def scheduling_reason(self) -> str:
        return self._result.scheduling_reason

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
    """SDK draft handle with one bounded released-shape construction edge."""

    __slots__ = (
        "_call_carrier",
        "_dispatcher",
        "_draft",
        "_legacy_tuple",
        "_metadata",
        "_sign",
    )

    @overload
    def __init__(
        self,
        tuple: InvocationTuple,
        metadata: Mapping[str, str] | None = None,
        sign: bool | None = None,
        call_carrier: DispatchCarrier = "unary",
        *,
        dispatcher: Dispatcher,
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        draft: easynet_sdk.InvocationDraft,
        sign: bool | None = None,
        call_carrier: DispatchCarrier = "unary",
        dispatcher: Dispatcher,
    ) -> None: ...

    def __init__(
        self,
        tuple: InvocationTuple | None = None,
        metadata: Mapping[str, str] | None = None,
        sign: bool | None = None,
        call_carrier: DispatchCarrier = "unary",
        *,
        draft: easynet_sdk.InvocationDraft | None = None,
        dispatcher: Dispatcher,
    ) -> None:
        if (tuple is None) == (draft is None):
            raise InvalidArgument(
                "exactly one of released tuple or SDK draft is required",
                reason="ambiguous_invocation_shape",
            )
        if tuple is not None and not isinstance(tuple, InvocationTuple):
            raise InvalidArgument(
                "released tuple must be an InvocationTuple",
                reason="invalid_invocation_tuple",
            )
        canonical = (
            _draft_from_legacy_tuple(tuple, metadata=metadata)
            if tuple is not None
            else draft
        )
        if not isinstance(canonical, easynet_sdk.InvocationDraft):
            raise InvalidArgument(
                "SDK InvocationDraft is required",
                reason="invalid_invocation_draft",
            )
        self._draft = canonical
        self._legacy_tuple = tuple
        self._metadata = dict(metadata) if metadata is not None else None
        self._sign = sign
        self._call_carrier = call_carrier
        self._dispatcher = dispatcher

    @property
    def draft(self) -> easynet_sdk.InvocationDraft:
        return self._draft

    @property
    def tuple(self) -> InvocationTuple | easynet_sdk.InvocationDraft:
        """Return the released view only for explicitly adapted callers."""

        return self._legacy_tuple or self._draft

    @property
    def metadata(self) -> Mapping[str, str] | None:
        return self._metadata

    @property
    def sign(self) -> bool | None:
        return self._sign

    @property
    def call_carrier(self) -> DispatchCarrier:
        return self._call_carrier

    def with_subject(self, ura: str) -> PreparedInvocation:
        if self._legacy_tuple is not None:
            return self._replace_legacy_tuple(
                replace(self._legacy_tuple, subject=ura),
            )
        return self._replace_draft(subject=ura)

    def with_causal(self, causal: LegacyCausal) -> PreparedInvocation:
        if self._legacy_tuple is not None:
            return self._replace_legacy_tuple(
                replace(self._legacy_tuple, causal=causal),
            )
        return self._replace_draft(causal=causal)

    def send(self) -> Invocation:
        return self._dispatcher(self)

    def _replace_draft(
        self,
        *,
        subject: str | None = None,
        causal: LegacyCausal | object = _UNSET,
    ) -> PreparedInvocation:
        return PreparedInvocation(
            draft=_adjust_sdk_draft(
                self._draft,
                subject=subject,
                causal=causal,
            ),
            sign=self.sign,
            call_carrier=self.call_carrier,
            dispatcher=self._dispatcher,
        )

    def _replace_legacy_tuple(
        self,
        tuple: InvocationTuple,
    ) -> PreparedInvocation:
        return PreparedInvocation(
            tuple,
            metadata=self.metadata,
            sign=self.sign,
            call_carrier=self.call_carrier,
            dispatcher=self._dispatcher,
        )


def _draft_from_legacy_tuple(
    tuple: InvocationTuple,
    *,
    metadata: Mapping[str, object] | None = None,
) -> easynet_sdk.InvocationDraft:
    projection = {
        "caller": tuple.caller,
        "callee": tuple.callee,
        "ability": _sdk_ability_selector(tuple.callee, tuple.ability),
        "subject": tuple.subject,
        "nonce": tuple.nonce,
        "causal": _sdk_causal_shape(tuple.causal),
        "arguments": tuple.arguments,
    }
    return _project_sdk_draft(projection, metadata=metadata)


def _adjust_sdk_draft(
    draft: easynet_sdk.InvocationDraft,
    *,
    subject: str | None,
    causal: LegacyCausal | object,
) -> easynet_sdk.InvocationDraft:
    arguments: dict[str, object] = {"content_type": draft.content_type}
    if draft.arguments_base64 is None:
        arguments["args"] = draft.args
    else:
        arguments["arguments_base64"] = draft.arguments_base64
    projection = {
        "caller": draft.caller_ura,
        "callee": draft.callee_ura,
        "ability": draft.descriptor_ref,
        "subject": subject if subject is not None else draft.subject_ura,
        "nonce": draft.nonce_base64,
        "causal": (
            draft.causal_context if causal is _UNSET else _sdk_causal_shape(causal)
        ),
        "arguments": arguments,
    }
    return _project_sdk_draft(
        projection,
        metadata=draft.metadata,
        caller_signature=draft.caller_signature,
    )


def _project_sdk_draft(
    projection: object,
    *,
    metadata: Mapping[str, object] | None = None,
    caller_signature: easynet_sdk.InvocationSignature | None = None,
) -> easynet_sdk.InvocationDraft:
    addressing = easynet_sdk.AddressingClient(easynet_sdk.AxonAddressingTransport())
    try:
        return easynet_sdk.InvocationWireProjector(addressing).build_invocation(
            projection,
            metadata=metadata,
            caller_signature=caller_signature,
        )
    except easynet_sdk.SDKError as exc:
        raise InvalidArgument(
            f"SDK rejected released Invocation adapter input: {exc}",
            reason="invalid_invocation_adjustment",
        ) from exc
    finally:
        addressing.close()


def _sdk_ability_selector(callee: str, ability: str) -> str:
    try:
        easynet_sdk.parse_ura(ability)
    except easynet_sdk.SDKError:
        try:
            easynet_sdk.project_descriptor_ref(ability)
        except easynet_sdk.SDKError:
            try:
                return easynet_sdk.owner_ability_ura(callee, ability)
            except easynet_sdk.SDKError as exc:
                raise InvalidArgument(
                    f"SDK rejected released ability selector: {exc}",
                    reason="invalid_ability_owner",
                ) from exc
    return ability


def _sdk_causal_shape(value: object) -> object:
    if isinstance(value, easynet_sdk.ReceiptReference):
        return CausalRef.from_sdk_reference(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(
            CausalRef.from_sdk_reference(reference)
            if isinstance(reference, easynet_sdk.ReceiptReference)
            else reference
            for reference in value
        )
    return value


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
