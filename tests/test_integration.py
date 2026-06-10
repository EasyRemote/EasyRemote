"""Integration suite against a live easynet-daemon (SPEC §10.2).

Read-only by design: it discovers and invokes query abilities, never
registers or mutates daemon state — the register→invoke loop is part
of the (manual, cleaned-up) P0 probe, not CI.

Activation requires all of:
- EASYNET_CLI_LIB pointing at a v3 libeasynet_cli, and
- a running daemon (~/.easynet/control.json + live pid).

Otherwise every test here skips with the reason shown.
"""

import json
import os
from pathlib import Path

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


def _an_agent_name() -> str:
    agents = json.loads((Path.home() / ".easynet" / "agents.json").read_text())
    names = sorted(agents.get("agents", {}))
    if not names:
        pytest.skip("no agents registered on this daemon")
    return names[0]


@pytest.fixture(scope="module")
def client():
    from easyremote.client import Client

    with Client(timeout=20.0) as live:
        yield live


def test_abi_handshake():
    from easyremote._transport import ABI_VERSION, abi

    abi.library()  # raises on version mismatch
    assert ABI_VERSION == 3


def test_transport_connects_to_live_daemon():
    from easyremote._transport import Transport

    with Transport.connect():
        pass


def test_discover_round_trip_and_receipt_shape(client):
    agent = _an_agent_name()
    invocation = client.invoke(f"{agent}.discover", scope="self", query="")

    assert invocation.state in (InvocationState.COMPLETED, InvocationState.UNSPECIFIED)
    result = invocation.result()
    assert isinstance(result, dict)
    assert "candidates" in result, f"discover shape drifted: {sorted(result)}"

    # P0 pin: does the daemon return an admission receipt summary on
    # the unary path, and does it parse through our wrapper?
    receipt = invocation.receipt
    if receipt is not None:
        assert receipt.invocation_id
        assert len(receipt.self_hash) == 32


def test_functions_facade_parses_live_candidates():
    # functions() routes through `<namespace>.discover` — point the
    # namespace at an agent this daemon actually registers (P0 pin:
    # unregistered namespaces are ROUTE_NEGATIVE, not empty results).
    from easyremote.client import Client

    with Client(timeout=20.0, namespace=_an_agent_name()) as scoped:
        infos = scoped.functions(scope="self")
    assert isinstance(infos, list)
    for info in infos:
        assert info.qualified_name.startswith("easynet:///r/")
