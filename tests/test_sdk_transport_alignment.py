"""EasyNet SDK ownership gates for the EasyRemote transport facade."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import easynet_sdk

from easyremote._sdk_transport import Transport
from easyremote.errors import Unavailable


class _RuntimeAbility:
    def __init__(self) -> None:
        self.draft = object()
        self.builds: list[tuple[object, str, object]] = []
        self.invocations: list[object] = []

    def build(self, call: object, ability: str, arguments: object) -> object:
        self.builds.append((call, ability, arguments))
        return self.draft

    def invoke_draft(self, draft: object) -> dict[str, object]:
        assert draft is self.draft
        self.invocations.append(draft)
        return {"ok": True}


def test_runtime_ability_builds_once_and_submits_the_same_draft() -> None:
    runtime_ability = _RuntimeAbility()
    transport = object.__new__(Transport)
    transport._runtime_ability = cast(Any, runtime_ability)
    call = cast(easynet_sdk.RuntimeCallContext, object())

    result = transport.invoke_runtime_ability(call, "agent.list", {"scope": "local"})

    assert result == {"ok": True}
    assert runtime_ability.builds == [(call, "agent.list", {"scope": "local"})]
    assert runtime_ability.invocations == [runtime_ability.draft]


def test_facade_has_no_credential_or_authority_policy_implementation() -> None:
    package = Path(__file__).parents[1] / "easyremote"
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in package.rglob("*.py")
    )

    assert "_read_credentials_metadata" not in sources
    assert "ManagedSigningClient" not in sources
    assert "mint_delegation_proof" not in sources
    assert 'scopes=("*",)' not in sources
    assert not (package / "_authority.py").exists()


def test_signed_unary_uses_provider_resolved_signer_not_requested_provider() -> None:
    requested = cast(easynet_sdk.Signer, object())
    active = cast(easynet_sdk.Signer, object())
    signers = _SignerProvider(active)
    adapter = _InvocationAdapter()
    transport = _signing_transport(adapter, signers)
    draft = cast(
        easynet_sdk.InvocationDraft,
        SimpleNamespace(caller_ura="easynet:///r/acme/user/alice"),
    )

    result = transport.invoke_signed(draft, signer=requested)

    assert result == {"ok": True}
    assert signers.requests == [(draft.caller_ura, requested)]
    assert adapter.signed_signers == [active]


def test_direct_stream_resolves_active_managed_signer_by_default() -> None:
    active = cast(easynet_sdk.Signer, object())
    signers = _SignerProvider(active)
    adapter = _InvocationAdapter()
    transport = _signing_transport(adapter, signers)
    draft = cast(
        easynet_sdk.InvocationDraft,
        SimpleNamespace(caller_ura="easynet:///r/acme/user/alice"),
    )

    stream = transport.stream(draft)

    assert stream is not None
    assert signers.requests == [(draft.caller_ura, None)]
    assert adapter.signed_signers == [active]
    assert adapter.unsigned_stream_calls == 0


def test_signed_dispatch_fails_closed_without_runtime_signer_provider() -> None:
    adapter = _InvocationAdapter()
    transport = _signing_transport(adapter, None)
    draft = cast(
        easynet_sdk.InvocationDraft,
        SimpleNamespace(caller_ura="easynet:///r/acme/user/alice"),
    )

    try:
        transport.invoke_signed(draft, signer=cast(easynet_sdk.Signer, object()))
    except Unavailable as exc:
        assert exc.reason == "caller_signer_unavailable"
    else:
        raise AssertionError("signed dispatch must require a runtime signer provider")

    assert adapter.signed_signers == []


class _SignerProvider:
    def __init__(self, active: easynet_sdk.Signer) -> None:
        self.active = active
        self.requests: list[tuple[str, easynet_sdk.Signer | None]] = []

    def resolve(
        self,
        caller_ura: str,
        requested: easynet_sdk.Signer | None = None,
    ) -> easynet_sdk.Signer:
        self.requests.append((caller_ura, requested))
        return self.active


class _InvocationAdapter:
    def __init__(self) -> None:
        self.signed_signers: list[easynet_sdk.Signer] = []
        self.unsigned_stream_calls = 0

    def invoke_signed(
        self,
        draft: easynet_sdk.InvocationDraft,
        *,
        signer: easynet_sdk.Signer,
    ) -> dict[str, bool]:
        del draft
        self.signed_signers.append(signer)
        return {"ok": True}

    def stream_signed(
        self,
        draft: easynet_sdk.InvocationDraft,
        *,
        signer: easynet_sdk.Signer,
    ) -> object:
        del draft
        self.signed_signers.append(signer)
        return object()

    def stream(self, draft: easynet_sdk.InvocationDraft) -> object:
        del draft
        self.unsigned_stream_calls += 1
        return object()


def _signing_transport(
    adapter: _InvocationAdapter,
    signers: _SignerProvider | None,
) -> Transport:
    transport = object.__new__(Transport)
    transport._adapter = cast(Any, adapter)
    transport._signers = cast(Any, signers)
    return transport
