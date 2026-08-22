"""EasyNet SDK ownership gates for the EasyRemote transport facade."""

from pathlib import Path
from typing import Any, cast

import easynet_sdk

from easyremote._sdk_transport import Transport


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
