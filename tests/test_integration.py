"""Integration suite against a live easynet-daemon (SPEC §10.2).

Read-only by default: the ordinary integration cases discover and invoke query
abilities. The raw-stream case performs a bounded register→invoke→uninstall
cycle only when ``EASYREMOTE_LIVE_RAW_STREAM=1`` is explicitly set.

Activation requires all of:
- EASYNET_CLI_LIB pointing at a compatible EasyNet-Cli SDK native library, and
- a running daemon (~/.easynet/control.json + live pid).

Otherwise every test here skips with the reason shown.
"""

import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import easynet_sdk
import pytest
from easynet_sdk import InvocationLifecycleState as InvocationState


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
    from easyremote._sdk_transport import Transport
    from easyremote.config import sdk_environment

    feature_set = sdk_environment().feature_set()
    assert feature_set.abi_version >= 4
    with Transport.connect():
        pass


def test_live_v8_raw_stream_preserves_exact_frames():
    if os.environ.get("EASYREMOTE_LIVE_RAW_STREAM") != "1":
        pytest.skip(
            "set EASYREMOTE_LIVE_RAW_STREAM=1 for the mutating raw-stream smoke"
        )

    from easyremote import (
        Client,
        ComputeNode,
        FreshRoot,
        ResolvedTargetSubject,
        StreamFrame,
    )
    from easyremote.config import sdk_environment

    environment = sdk_environment()
    try:
        features = environment.feature_set()
    finally:
        environment.close()
    assert features.abi_version == 7
    assert features.axon_pb is True
    assert features.symbols.get("stream_raw_payload_v8") is True

    payloads = [bytes(range(256)) * 64, b"\x00\xffh264\x00frame", b""]
    # Deliberately place the package under the EasyRemote checkout rather than
    # the daemon's cwd. Installation must stage bytes through fs.transfer; a
    # client-authored fs/workspace ResourceRef would resolve against the wrong
    # process root and make this live smoke fail.
    runtime_root = Path.cwd() / "target" / "live-smoke"
    runtime_root.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="easyremote-v8-", dir=runtime_root))
    short_root = Path(tempfile.mkdtemp(prefix="er-v8-link-"))
    linked_root = short_root / "root"
    linked_root.symlink_to(root, target_is_directory=True)
    namespace = f"erv8smoke{os.getpid()}"
    node = ComputeNode(namespace=namespace, abilities_dir=linked_root / "abilities")

    @node.register(name="raw_frames")
    def raw_frames() -> Iterator[StreamFrame]:
        for payload in payloads:
            yield StreamFrame(payload, "application/vnd.easynet.raw-smoke")

    try:
        node.start()
        ability_ura = node.abilities[0].ura
        assert ability_ura is not None
        with Client(
            timeout=20.0,
            invocation_policy=FreshRoot(ResolvedTargetSubject()),
        ) as live:
            received = list(live.stream(ability_ura))
        assert received == [
            StreamFrame(payload, "application/vnd.easynet.raw-smoke")
            for payload in payloads
        ]
    finally:
        try:
            node.stop()
        finally:
            shutil.rmtree(short_root, ignore_errors=True)
            shutil.rmtree(root, ignore_errors=True)


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
