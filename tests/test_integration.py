"""Integration suite against a live easynet-daemon (SPEC §10.2).

Read-only by design: it discovers and invokes query abilities, never
registers or mutates daemon state — the register→invoke loop is part
of the (manual, cleaned-up) P0 probe, not CI.

Activation requires all of:
- EASYNET_CLI_LIB pointing at a compatible EasyNet-Cli SDK native library, and
- a running daemon (~/.easynet/control.json + live pid).

Otherwise every test here skips with the reason shown.
"""

import json
import os
from pathlib import Path

import easynet_sdk
import pytest

from easyremote.receipts import InvocationState


def _live_daemon_available() -> str | None:
    if not os.environ.get("EASYNET_CLI_LIB"):
        return "EASYNET_CLI_LIB not set"
    control = Path.home() / ".easynet" / "control.json"
    if not control.exists():
        return "no ~/.easynet/control.json (daemon not set up)"
    try:
        pid = json.loads(control.read_text()).get("pid")
        os.kill(int(pid), 0)
    except (ValueError, TypeError, ProcessLookupError, PermissionError):
        return "daemon pid not alive"
    return None


_SKIP_REASON = _live_daemon_available()
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(_SKIP_REASON is not None, reason=_SKIP_REASON or ""),
]


def _an_agent_ura() -> str:
    registry = Path.home() / ".easynet" / "local-agents.json"
    if not registry.exists():
        pytest.skip(
            "no daemon-owned hosted-agent registry at ~/.easynet/local-agents.json"
        )
    hosted = json.loads(registry.read_text()).get("hosted_agents", [])
    agent_uras = sorted(
        row.get("agent_ura", "") for row in hosted if row.get("profile") == "llm"
    )
    if not agent_uras:
        pytest.skip("no hosted LLM agents registered on this daemon")
    return agent_uras[0]


def _agent_ability_ura(agent_ura: str, ability: str) -> str:
    try:
        ability_ura = easynet_sdk.owner_ability_ura(agent_ura, ability)
    except easynet_sdk.SDKError:
        pytest.skip(f"cannot build Ability URA for {agent_ura}#{ability}")
    return ability_ura


@pytest.fixture(scope="module")
def client():
    from easyremote.client import Client
    from easyremote.invocation_policy import FreshRoot, ResolvedTargetSubject

    with Client(
        timeout=20.0,
        invocation_policy=FreshRoot(ResolvedTargetSubject()),
    ) as live:
        yield live


def test_sdk_transport_connects_to_live_daemon():
    import easynet_sdk

    from easyremote._sdk_transport import Transport

    feature_set = easynet_sdk.SdkEnvironment().feature_set()
    assert feature_set.abi_version >= 4
    with Transport.connect():
        pass


def test_discover_round_trip_and_receipt_shape(client):
    invocation = client.invoke(
        _agent_ability_ura(_an_agent_ura(), "discover"),
        scope="self",
        query="",
    )

    assert invocation.state is InvocationState.COMPLETED
    result = invocation.result()
    assert isinstance(result, dict)
    assert "candidates" in result, f"discover shape drifted: {sorted(result)}"

    # P0 pin: does the daemon return an admission receipt summary on
    # the unary path, and does it parse through our wrapper?
    receipt = invocation.receipt
    assert isinstance(receipt, easynet_sdk.RuntimeReceipt)
    assert receipt.invocation_id
    assert len(receipt.self_receipt_hash()) == 32


def test_functions_facade_parses_live_candidates():
    # Bind the namespace to a canonical owner URA. The fixture may read
    # daemon state to select a sample, but the SDK runtime must not guess
    # `caesura -> easynet:///.../agent/dev.caesura` itself.
    from easyremote.client import Client
    from easyremote.invocation_policy import FreshRoot, ResolvedTargetSubject

    with Client(
        timeout=20.0,
        namespace=_an_agent_ura(),
        invocation_policy=FreshRoot(ResolvedTargetSubject()),
    ) as scoped:
        infos = scoped.functions(scope="self")
    assert isinstance(infos, list)
    for info in infos:
        assert info.ability_ura.startswith("easynet:///r/")
