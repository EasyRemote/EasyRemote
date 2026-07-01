"""Invocation data model and wire codec (SPEC §5.7).

The seven-tuple lives here as :class:`InvocationTuple` — always
inspectable (design invariant 2), never hidden inside a string. The
wire encoding targets the libeasynet_cli invocation JSON exactly as
parsed by ``EasyNet-Cli/src/ffi/invocation.rs::InvocationJson::parse``:

- ``descriptor_ref``: ``<owner ability URA>@<descriptor version>``;
  derived from ``callee`` + ``ability`` + ``descriptor_version`` when the
  tuple carries a bare route name
- ``nonce_base64``: 16 bytes, standard base64, never all-zero
- ``causal_context``: ``{"form": none|scalar|list|merkle, ...}`` with
  hex-encoded 32-byte hashes
- ``args`` (JSON) XOR ``arguments_base64`` + ``content_type``
- optional ``metadata``, ``caller_signature``, ``bidi_streams``

This module owns data and codec only. Dispatching belongs to the
client layer, which injects a dispatcher into
:class:`PreparedInvocation`; URA validity is enforced by the daemon
and by the builders that produce URAs — never re-derived here.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from easynet_axon import ura as axon_ura
from easynet_axon.invocation.axiom import canonical_ability_descriptor_ref
from easynet_axon.invocation.error import AxonError

from ._json import dumps_wire
from .errors import InternalError, InvalidArgument
from .receipts import InvocationState, Receipt, ReceiptChain

__all__ = [
    "Arguments",
    "CallerSignature",
    "CausalRef",
    "DispatchCarrier",
    "Invocation",
    "InvocationTuple",
    "MerkleAnchor",
    "PreparedInvocation",
    "StreamSpec",
    "encode_invocation",
    "fresh_nonce",
]

JSON_CONTENT_TYPE = "application/json"

# Default ability descriptor version the daemon assigns to a device
# ability at registration (EasyNet-Cli
# `DEFAULT_ABILITY_DESCRIPTOR_VERSION`). A call binds against the
# descriptor at this version; the daemon adopts the value when the
# ability has not pinned a different one.
DEFAULT_DESCRIPTOR_VERSION = "1.0.0"


def fresh_nonce() -> bytes:
    """16 random bytes, never all-zero (wire contract)."""
    while True:
        nonce = os.urandom(16)
        if any(nonce):
            return nonce


@dataclass(frozen=True)
class Arguments:
    """Ability arguments: JSON by default, raw bytes by explicit opt-in.

    Exactly one of ``json_value``/``raw`` is populated — mirroring the
    wire rule "provide exactly one of `args` or `arguments_base64`".
    """

    content_type: str
    json_value: Any = None
    raw: bytes | None = None

    @classmethod
    def from_json(cls, value: Any) -> Arguments:
        return cls(content_type=JSON_CONTENT_TYPE, json_value=value)

    @classmethod
    def from_bytes(cls, data: bytes, content_type: str) -> Arguments:
        if not content_type.strip():
            raise InvalidArgument(
                "binary arguments need an explicit content_type",
                reason="missing_content_type",
            )
        return cls(content_type=content_type.strip(), raw=data)

    @property
    def is_json(self) -> bool:
        return self.raw is None

    def canonical_bytes(self) -> bytes:
        if self.raw is not None:
            return self.raw
        return dumps_wire(self.json_value, what="invocation arguments").encode("utf-8")

    def digest(self) -> bytes:
        """SHA-256 of the canonical argument bytes (the tuple's args_digest)."""
        return hashlib.sha256(self.canonical_bytes()).digest()


@dataclass(frozen=True)
class CausalRef:
    """A reference to one prior receipt (the ``scalar``/``list`` forms).

    ``receipt_ura`` must come from the daemon or an Axon builder — the
    receipt-body URA shape is a flagged SPEC §6 gap, so this package
    never fabricates one from a receipt summary.
    """

    receipt_hash: bytes
    receipt_ura: str

    def __post_init__(self) -> None:
        if len(self.receipt_hash) != 32:
            raise InvalidArgument(
                f"receipt_hash must be 32 bytes, got {len(self.receipt_hash)}",
                reason="invalid_receipt_hash",
            )
        if not self.receipt_ura.strip():
            raise InvalidArgument(
                "receipt_ura must not be empty", reason="invalid_receipt_ura"
            )

    def to_wire(self) -> dict[str, str]:
        return {
            "receipt_hash_hex": self.receipt_hash.hex(),
            "receipt_ura": self.receipt_ura,
        }


@dataclass(frozen=True)
class MerkleAnchor:
    """Compact causal placement: a Merkle root plus a proof artifact URA."""

    root: bytes
    proof_ura: str

    def __post_init__(self) -> None:
        if len(self.root) != 32:
            raise InvalidArgument(
                f"merkle root must be 32 bytes, got {len(self.root)}",
                reason="invalid_merkle_root",
            )
        if not self.proof_ura.strip():
            raise InvalidArgument(
                "proof_ura must not be empty", reason="invalid_proof_ura"
            )


# The caller-declared causal placement: empty, one receipt, a bounded
# list, or a Merkle anchor (Invocation Axiom, causal_context field).
Causal = CausalRef | Sequence[CausalRef] | MerkleAnchor | None


def _encode_causal(causal: Causal) -> dict[str, Any]:
    if causal is None:
        return {"form": "none"}
    if isinstance(causal, CausalRef):
        return {"form": "scalar", **causal.to_wire()}
    if isinstance(causal, MerkleAnchor):
        return {
            "form": "merkle",
            "root_hex": causal.root.hex(),
            "proof_ura": causal.proof_ura,
        }
    refs = list(causal)
    if not refs:
        raise InvalidArgument(
            "causal list must not be empty — use None for a root invocation",
            reason="empty_causal_list",
        )
    return {"form": "list", "prior": [ref.to_wire() for ref in refs]}


@dataclass(frozen=True)
class CallerSignature:
    """An already-produced Ed25519 signature carried on the envelope.

    Producing signatures is easynet_axon's job (canonical bytes +
    signing); this type only transports the result.
    """

    algorithm: str
    signature: bytes
    key_id_hint: str = ""

    def to_wire(self) -> dict[str, str]:
        return {
            "algorithm": self.algorithm,
            "signature_base64": base64.b64encode(self.signature).decode("ascii"),
            "key_id_hint": self.key_id_hint,
        }


@dataclass(frozen=True)
class StreamSpec:
    """One declared bidi stream (frame-0 ``StreamDescriptor``)."""

    stream_id: int
    content_type: str
    ordering: str = "STRICT"
    codec_params: str = ""

    def to_wire(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "content_type": self.content_type,
            "ordering": self.ordering,
            "codec_params": self.codec_params,
        }


@dataclass(frozen=True)
class InvocationTuple:
    """The Axon seven-tuple: caller, callee, ability, subject, nonce,
    causal context, arguments.

    Always fully readable — convenience defaults upstream (subject =
    callee, causal = None) land here as explicit values, never as
    hidden wire-time substitutions.
    """

    caller: str
    callee: str
    ability: str
    subject: str
    nonce: bytes
    causal: Causal
    arguments: Arguments

    def __post_init__(self) -> None:
        for name in ("caller", "callee", "ability", "subject"):
            if not getattr(self, name).strip():
                raise InvalidArgument(
                    f"{name} must not be empty", reason=f"empty_{name}"
                )
        if len(self.nonce) != 16:
            raise InvalidArgument(
                f"nonce must be 16 bytes, got {len(self.nonce)}",
                reason="invalid_nonce",
            )
        if not any(self.nonce):
            raise InvalidArgument("nonce must not be all-zero", reason="zero_nonce")

    @property
    def args_digest(self) -> bytes:
        return self.arguments.digest()


def encode_invocation(
    tuple_: InvocationTuple,
    *,
    metadata: Mapping[str, str] | None = None,
    caller_signature: CallerSignature | None = None,
    bidi_streams: Sequence[StreamSpec] | None = None,
    descriptor_version: str = DEFAULT_DESCRIPTOR_VERSION,
) -> dict[str, Any]:
    """Encode the seven-tuple (plus transport extras) to the FFI wire dict.

    The seven-tuple's ability identity reaches the daemon only as the
    descriptor-bound ``descriptor_ref`` (``<owner ability URA>@<version>``);
    ``InvocationJson::parse`` reads neither a bare ``ability`` field nor a
    separate ``descriptor_version``, so this codec emits neither.
    ``descriptor_version`` is the version this codec binds into the ref —
    NOT an eighth tuple field. The inspectable route name stays on the
    in-memory ``InvocationTuple.ability`` for diagnostics.
    """
    descriptor_ref = _descriptor_ref_for_wire(tuple_, descriptor_version)
    wire: dict[str, Any] = {
        "caller_ura": tuple_.caller,
        "callee_ura": tuple_.callee,
        "descriptor_ref": descriptor_ref,
        "subject_ura": tuple_.subject,
        "nonce_base64": base64.b64encode(tuple_.nonce).decode("ascii"),
        "causal_context": _encode_causal(tuple_.causal),
    }
    if tuple_.arguments.is_json:
        wire["args"] = tuple_.arguments.json_value
    else:
        wire["arguments_base64"] = base64.b64encode(tuple_.arguments.raw or b"").decode(
            "ascii"
        )
        wire["content_type"] = tuple_.arguments.content_type
    if metadata:
        wire["metadata"] = dict(metadata)
    if caller_signature is not None:
        wire["caller_signature"] = caller_signature.to_wire()
    if bidi_streams:
        wire["bidi_streams"] = [stream.to_wire() for stream in bidi_streams]
    return wire


def _descriptor_ref_for_wire(
    tuple_: InvocationTuple, descriptor_version: str
) -> str:
    """Derive the canonical ``descriptor_ref`` the daemon binds against.

    A tuple route name (``observe.health``) is projected onto the
    callee-owned Ability URA at ``descriptor_version``; an ability that
    already carries an explicit descriptor ref passes through with its
    own pinned version. The daemon independently re-derives the owner
    from this ref and rejects it unless it matches ``callee`` — so the
    facade never reasons about owner/callee agreement itself.
    """
    version = descriptor_version.strip()
    if not version:
        raise InvalidArgument(
            "descriptor_version must not be empty",
            reason="empty_descriptor_version",
        )

    ability = tuple_.ability.strip()
    try:
        descriptor_ref = canonical_ability_descriptor_ref(ability)
    except AxonError:
        ability_ura = axon_ura.owner_ability_ura(tuple_.callee, ability)
        if ability_ura is None:
            raise InvalidArgument(
                "cannot derive descriptor_ref from callee/ability:"
                f" callee={tuple_.callee!r}, ability={ability!r}",
                reason="descriptor_ref_derivation_failed",
            ) from None
        descriptor_ref = f"{ability_ura}@{version}"

    try:
        return str(canonical_ability_descriptor_ref(descriptor_ref))
    except AxonError as exc:
        raise InvalidArgument(
            f"descriptor_ref is rejected by Axon: {exc}",
            reason="invalid_descriptor_ref",
        ) from exc


class Invocation:
    """A dispatched unary invocation and its daemon response.

    C ABI v3 unary invoke is synchronous — by the time this object
    exists the invocation reached a terminal state, so ``result()``
    never blocks. The response summary shape comes from
    ``ffi/invocation.rs::invocation_output_json``.
    """

    def __init__(self, tuple_: InvocationTuple, response: dict[str, Any]) -> None:
        if not response.get("ok", False):
            raise InternalError(
                "non-ok invoke response reached Invocation — transport should"
                f" have raised: {response}",
                reason="protocol",
            )
        self._tuple = tuple_
        self._response = response

    @property
    def tuple(self) -> InvocationTuple:
        return self._tuple

    @property
    def id(self) -> str:
        """Invocation id, when the daemon returned an admission receipt."""
        receipt = self.receipt
        return receipt.invocation_id if receipt else ""

    @property
    def state(self) -> InvocationState:
        try:
            return InvocationState(int(self._response.get("state", 0)))
        except ValueError:
            return InvocationState.UNSPECIFIED

    def result(self) -> Any:
        """The ability's return value: JSON-decoded, or raw bytes for
        non-JSON content types. Shell-executor envelopes are unwrapped
        (the raw envelope stays available via :attr:`raw_response`)."""
        content_type = self._response.get("result_content_type", "")
        if content_type == JSON_CONTENT_TYPE:
            if self._response.get("result_json") is not None:
                return _unwrap_executor_envelope(self._response["result_json"])
            data = self._decoded_result_bytes()
            return _unwrap_executor_envelope(json.loads(data)) if data else None
        return self._decoded_result_bytes()

    @property
    def receipt(self) -> Receipt | None:
        """The admission receipt summary, when the daemon returned one."""
        wire = self._response.get("admission_receipt")
        return Receipt.from_wire(wire) if wire else None

    def receipts(self) -> ReceiptChain:
        receipt = self.receipt
        return ReceiptChain([receipt] if receipt else [])

    @property
    def selected_node_id(self) -> str:
        return str(self._response.get("selected_node_id", ""))

    @property
    def scheduling_reason(self) -> str:
        return str(self._response.get("scheduling_reason", ""))

    @property
    def elapsed_ms(self) -> int:
        return int(self._response.get("elapsed_ms", 0))

    @property
    def raw_response(self) -> dict[str, Any]:
        return self._response

    def _decoded_result_bytes(self) -> bytes:
        encoded = self._response.get("result_base64", "")
        return base64.b64decode(encoded) if encoded else b""


def _unwrap_executor_envelope(value: Any) -> Any:
    """Unwrap standard daemon executor/registry result envelopes.

    Shell-executor abilities return ``{fulfilled_by, exit_code,
    elapsed_ms, sandboxed, result: "<stdout string>"}``; the actual
    value is JSON text inside ``result``. The daemon ``<self>.invoke``
    ability returns ``{result, fulfilled_by, target, ability,
    qualified_name, elapsed_ms}``; result-first clients should see the
    inner ability result, not the routing envelope. System abilities
    (e.g. discover) return their JSON directly and pass through.
    """
    if (
        isinstance(value, dict)
        and "fulfilled_by" in value
        and "exit_code" in value
        and isinstance(value.get("result"), str)
    ):
        try:
            return json.loads(value["result"])
        except json.JSONDecodeError:
            return value["result"]  # plain-text stdout abilities
    if isinstance(value, dict) and "fulfilled_by" in value and "result" in value:
        return value["result"]
    return value


DispatchCarrier = Literal["stream", "unary"]
Dispatcher = Callable[["PreparedInvocation"], Invocation]


@dataclass(frozen=True)
class PreparedInvocation:
    """Built but not yet dispatched — the inspect-before-send hook.

    ``with_causal`` takes :class:`CausalRef`/:class:`MerkleAnchor`
    values rather than bare receipts: turning a receipt summary into a
    causal reference needs the receipt URA, whose canonical shape is
    the flagged SPEC §6 gap.
    """

    tuple: InvocationTuple
    metadata: Mapping[str, str] | None = None
    sign: bool | None = None
    call_carrier: DispatchCarrier = "unary"
    dispatcher: Dispatcher = field(repr=False, compare=False, kw_only=True)

    def with_subject(self, ura: str) -> PreparedInvocation:
        return replace(self, tuple=replace(self.tuple, subject=ura))

    def with_causal(self, causal: Causal) -> PreparedInvocation:
        return replace(self, tuple=replace(self.tuple, causal=causal))

    def send(self) -> Invocation:
        return self.dispatcher(self)
