"""Private transport layer over the EasyNet-Cli SDK facade.

EasyRemote keeps its historical ``Transport``/``FrameStream`` shape, but daemon
I/O now enters through ``easynet_sdk``. Raw C ABI loading, unary wait state, and
bidi session lifecycle semantics are owned by the SDK package, not by
EasyRemote.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

import easynet_sdk

from ..config import sdk_environment
from ..errors import error_from_sdk

__all__ = [
    "FrameStream",
    "Transport",
    "UnaryDispatchPool",
]


class Transport:
    """SDK-owned draft provider and Invocation transport."""

    def __init__(
        self,
        adapter: easynet_sdk.InvocationResultAdapter,
        addressing: easynet_sdk.AddressingClient,
        authority: easynet_sdk.DraftAuthorityProvider,
        *,
        signers: easynet_sdk.RuntimeSignerProvider | None = None,
        environment: easynet_sdk.SdkEnvironment | None = None,
    ) -> None:
        self._adapter = adapter
        self._addressing = addressing
        self._invoker = easynet_sdk.AbilityInvocationClient(
            adapter.transport.runtime,
            addressing,
            authority,
        )
        self._runtime_ability = easynet_sdk.RuntimeAbilityClient(
            adapter.transport.runtime,
            addressing,
            authority,
        )
        self._descriptor_provider = easynet_sdk.RuntimeAbilityDescriptorProvider(
            self._runtime_ability,
        )
        self._receipt_provider = easynet_sdk.RuntimeReceiptProvider(
            self._runtime_ability
        )
        self._signers = signers
        self._environment = environment

    @classmethod
    def connect(cls, control_path: str | None = None) -> Transport:
        environment = sdk_environment(control_path=control_path)
        try:
            adapter = easynet_sdk.InvocationResultAdapter.connect(
                control_path=environment.resolved_control_path(),
                library_path=environment.library_path,
            )
            addressing = environment.addressing_client()
            return cls(
                adapter,
                addressing,
                environment.local_runtime_authority_provider(addressing),
                signers=environment.local_runtime_signer_provider(),
                environment=environment,
            )
        except easynet_sdk.SDKError as exc:
            environment.close()
            raise error_from_sdk(exc) from exc

    def build_invocation(
        self,
        request: easynet_sdk.AbilityCallRequest,
    ) -> easynet_sdk.InvocationDraft:
        """Delegate explicit-callee Invocation construction to the SDK."""
        try:
            return self._invoker.build_invocation(request)
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def invoke_runtime_ability(
        self,
        call: easynet_sdk.RuntimeCallContext,
        ability_name: str,
        arguments: object,
    ) -> dict[str, Any]:
        try:
            draft = self._runtime_ability.build(call, ability_name, arguments)
            return dict(self._runtime_ability.invoke_draft(draft))
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def open_runtime_ability_bidi(
        self,
        call: easynet_sdk.RuntimeCallContext,
        ability_name: str,
        arguments: object,
        streams: Iterable[easynet_sdk.BidiStreamDescriptor],
    ) -> easynet_sdk.BidiSession:
        """Open one daemon system ability through its committed bidi descriptor."""
        try:
            return self._runtime_ability.open_bidi(
                call,
                ability_name,
                arguments,
                tuple(streams),
            )
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def list_ability_descriptors(
        self,
        call: easynet_sdk.RuntimeCallContext,
        *,
        scope: str = "",
        owner_ura: str = "",
        ability_ura: str = "",
    ) -> list[dict[str, Any]]:
        try:
            page = self._descriptor_provider.list(
                easynet_sdk.AbilityDescriptorListRequest(
                    call=call,
                    scope=scope,
                    owner_ura=owner_ura,
                    ability_ura=ability_ura,
                )
            )
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc
        return [_ability_descriptor_row(descriptor) for descriptor in page.descriptors]

    def get_ability_descriptor(
        self,
        call: easynet_sdk.RuntimeCallContext,
        *,
        ability_ura: str,
        call_mode: str = "",
        descriptor_version: str = "",
        scope: str = "",
    ) -> dict[str, Any]:
        try:
            descriptor = self._descriptor_provider.get(
                easynet_sdk.AbilityDescriptorGetRequest(
                    call=call,
                    ability_ura=ability_ura,
                    call_mode=call_mode,
                    descriptor_version=descriptor_version,
                    scope=scope,
                )
            )
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc
        return _ability_descriptor_row(descriptor)

    def invocation_trace(
        self,
        call: easynet_sdk.RuntimeCallContext,
        *,
        request_id: str,
    ) -> easynet_sdk.InvocationTraceGraph:
        try:
            result = self._receipt_provider.trace(
                easynet_sdk.ReceiptTraceRequest(
                    call=call,
                    lookup=easynet_sdk.ReceiptLookup(request_id=request_id),
                )
            )
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc
        return result.graph

    def invoke(
        self,
        invocation: easynet_sdk.InvocationDraft,
    ) -> dict[str, Any]:
        try:
            return dict(self._adapter.invoke(invocation))
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def invoke_signed(
        self,
        invocation: easynet_sdk.InvocationDraft,
        *,
        signer: easynet_sdk.Signer | None,
    ) -> dict[str, Any]:
        try:
            resolved_signer = self._resolve_signer(invocation, signer)
            return dict(
                self._adapter.invoke_signed(invocation, signer=resolved_signer)
            )
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def stream(
        self,
        invocation: easynet_sdk.InvocationDraft,
        *,
        signer: easynet_sdk.Signer | None = None,
    ) -> FrameStream:
        try:
            if self._signers is None:
                return FrameStream(self._adapter.stream(invocation))
            resolved_signer = self._resolve_signer(invocation, signer)
            return FrameStream(
                self._adapter.stream_signed(
                    invocation,
                    signer=resolved_signer,
                )
            )
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def _resolve_signer(
        self,
        invocation: easynet_sdk.InvocationDraft,
        requested: easynet_sdk.Signer | None,
    ) -> easynet_sdk.Signer:
        if self._signers is None:
            raise easynet_sdk.SDKError(
                code=easynet_sdk.ErrorCode.CALLER_SIGNER_UNAVAILABLE,
                stage="runtime_signer",
                retry=easynet_sdk.RetryHint.NEVER,
                retryable=False,
                message="local runtime signer provider is unavailable",
            )
        return self._signers.resolve(invocation.caller_ura, requested)

    def bidi(
        self,
        invocation: easynet_sdk.InvocationDraft,
        streams: Iterable[easynet_sdk.BidiStreamDescriptor],
    ) -> easynet_sdk.RuntimeBidiChannel:
        try:
            return self._adapter.bidi(invocation, streams)
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def close(self) -> None:
        first_error: easynet_sdk.SDKError | None = None
        try:
            self._adapter.close()
        except easynet_sdk.SDKError as exc:
            first_error = exc
        try:
            self._addressing.close()
        except easynet_sdk.SDKError as exc:
            if first_error is None:
                first_error = exc
        if self._environment is not None:
            try:
                self._environment.close()
            except easynet_sdk.SDKError as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise error_from_sdk(first_error) from first_error

    def __enter__(self) -> Transport:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class UnaryDispatchPool:
    """EasyRemote error-mapping wrapper over the SDK unary dispatch pool."""

    def __init__(self, pool: easynet_sdk.UnaryDispatchPool) -> None:
        self._pool = pool

    @classmethod
    def connect(cls) -> UnaryDispatchPool:
        def factory() -> easynet_sdk.UnaryInvocationTransport:
            return cast(easynet_sdk.UnaryInvocationTransport, Transport.connect())

        return cls(easynet_sdk.UnaryDispatchPool(factory))

    @classmethod
    def from_transport(cls, transport: Transport) -> UnaryDispatchPool:
        return cls(
            easynet_sdk.UnaryDispatchPool.from_transport(
                cast(easynet_sdk.UnaryInvocationTransport, transport)
            )
        )

    def invoke(
        self,
        invocation: easynet_sdk.InvocationDraft,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        try:
            return dict(self._pool.invoke(invocation, timeout=timeout))
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def invoke_signed(
        self,
        invocation: easynet_sdk.InvocationDraft,
        *,
        signer: easynet_sdk.Signer | None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        try:
            return dict(
                self._pool.invoke_signed(
                    invocation,
                    signer=signer,
                    timeout=timeout,
                )
            )
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def close(self) -> None:
        try:
            self._pool.close()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    @property
    def current_transport(self) -> Transport | None:
        return cast(Transport | None, self._pool.current_transport)

    def connected_transport(self) -> Transport:
        return cast(Transport, self._pool.connected_transport())


@dataclass
class FrameStream:
    """Server-stream wrapper that preserves EasyRemote's frame API."""

    _stream: easynet_sdk.RuntimeFrameStream

    def recv(self, timeout: float | None = None) -> dict[str, Any] | None:
        try:
            return dict(self._stream.recv(timeout=timeout))
        except StopIteration:
            return None
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def close(self) -> None:
        try:
            self._stream.close()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def __enter__(self) -> FrameStream:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _ability_descriptor_row(
    descriptor: easynet_sdk.AbilityDescriptorProjection,
) -> dict[str, Any]:
    return {
        "name": descriptor.name,
        "ability_ura": descriptor.ability_ura,
        "descriptor_ref": descriptor.descriptor_ref,
        "owner_ura": descriptor.owner_ura,
        "descriptor_version": descriptor.version,
        "call_mode": descriptor.call_mode,
        "description": descriptor.description,
        "input_schema": dict(descriptor.input_schema),
        "metadata": dict(descriptor.metadata),
    }
