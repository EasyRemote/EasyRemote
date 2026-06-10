"""ComputeNode: manifest materialization, rejections, lifecycle."""

import json
import sys
from collections.abc import Iterator

import pytest
import tomllib

from easyremote._host.forward import main as forward_main
from easyremote.context import Context
from easyremote.errors import InvalidArgument, Unavailable
from easyremote.node import ComputeNode


@pytest.fixture()
def node(tmp_path):
    return ComputeNode(agents_root=tmp_path / "agents")


def read_manifest(info):
    return tomllib.loads(info.manifest_path.read_text())


def test_register_writes_pinned_manifest_shape(node):
    @node.register
    def ai_inference(prompt: str, max_tokens: int = 64) -> str:
        """Generate a completion on this device."""
        return prompt

    manifest = read_manifest(ai_inference.info)
    assert manifest["schema_version"] == "1"
    assert manifest["name"] == "ai_inference"
    assert manifest["description"] == "Generate a completion on this device."
    assert manifest["exec"]["kind"] == "shell"

    argv = manifest["exec"]["argv"]
    assert argv[0] == sys.executable
    assert argv[1:3] == ["-m", "easyremote._host.forward"]
    assert argv[4] == "ai_inference"
    assert argv[5:] == ["{{ prompt }}", "{{ max_tokens }}"]

    schema = manifest["input_schema"]
    # Executor constraint: every parameter required; default advertised.
    assert schema["required"] == ["prompt", "max_tokens"]
    assert schema["properties"]["max_tokens"]["default"] == 64
    assert manifest["output_schema"] == {"type": "string"}
    assert ai_inference.info.manifest_path.name == "ai_inference.ability.toml"
    assert ai_inference.info.manifest_path.parent.name == "abilities"


def test_qualified_name_uses_namespace(node):
    @node.register
    def fn(a: int) -> int:
        return a

    assert fn.qualified_name == "er.fn"
    assert node.abilities[0].qualified_name == "er.fn"


def test_decorator_with_options_and_timeout(node):
    @node.register(name="custom", description="d", timeout=2.5)
    def fn(a: int) -> int:
        return a

    manifest = read_manifest(fn.info)
    assert manifest["name"] == "custom"
    assert manifest["timeout_seconds"] == 3  # ceil(2.5)


def test_registered_function_still_callable_locally(node):
    @node.register
    def double(x: int) -> int:
        return x * 2

    assert double(21) == 42


def test_stream_function_rejected_with_enabler_pointer(node):
    def chunks(n: int) -> Iterator[str]:
        yield "x"

    with pytest.raises(Unavailable) as exc_info:
        node.register(chunks)
    assert exc_info.value.reason == "stream_requires_host_attach"
    assert "PR-1" in str(exc_info.value)


def test_context_function_rejected_with_enabler_pointer(node):
    def report(ctx: Context, q: str) -> str:
        return q

    with pytest.raises(Unavailable) as exc_info:
        node.register(report)
    assert exc_info.value.reason == "context_requires_host_attach"


def test_duplicate_and_invalid_names_rejected(node):
    @node.register
    def fn(a: int) -> int:
        return a

    with pytest.raises(InvalidArgument, match="already registered"):
        node.register(lambda a: a, name="fn", schema={"type": "object"})
    with pytest.raises(InvalidArgument, match="namespace separators"):
        node.register(lambda a: a, name="bad.name", schema={"type": "object"})


def test_invalid_namespace_rejected(tmp_path):
    with pytest.raises(InvalidArgument, match="namespace"):
        ComputeNode(namespace="er.bad", agents_root=tmp_path)


# -- daemon-managed root mode (agents.json + refresh) --------------------------


def daemon_managed_node(tmp_path, monkeypatch, registered=True):
    import easyremote.config as config

    monkeypatch.setattr(config, "agents_root", lambda: tmp_path / "agents")
    if registered:
        agent_root = tmp_path / "managed-root"
        (tmp_path / "agents.json").write_text(
            json.dumps({"agents": {"er": {"root_path": str(agent_root)}}})
        )
    cli_calls = []
    node = ComputeNode(cli_runner=cli_calls.append)
    return node, cli_calls, tmp_path / "managed-root"


def test_registered_agent_root_is_read_back_not_assumed(tmp_path, monkeypatch):
    node, _, agent_root = daemon_managed_node(tmp_path, monkeypatch)

    @node.register
    def fn(a: int) -> int:
        return a

    assert fn.info.manifest_path == agent_root / "abilities" / "fn.ability.toml"


def test_unregistered_agent_is_actionable(tmp_path, monkeypatch):
    node, _, _ = daemon_managed_node(tmp_path, monkeypatch, registered=False)
    with pytest.raises(Unavailable) as exc_info:
        node.register(lambda a: a, name="fn", schema={"type": "object"})
    assert exc_info.value.reason == "agent_not_registered"
    assert "easynet agent add" in str(exc_info.value)


def test_start_and_post_start_register_announce_via_refresh(
    tmp_path, monkeypatch, short_tmp
):
    import easyremote.config as config

    monkeypatch.setattr(config, "agents_root", lambda: tmp_path / "agents")
    agent_root = short_tmp / "managed"  # short: the host socket binds here
    (tmp_path / "agents.json").write_text(
        json.dumps({"agents": {"er": {"root_path": str(agent_root)}}})
    )
    cli_calls = []
    node = ComputeNode(cli_runner=cli_calls.append)

    node.register(lambda a: a, name="before", schema={"type": "object"})
    assert cli_calls == []  # nothing announced before start

    with node:
        assert cli_calls == [["agent", "refresh", "--agent", "er"]]
        node.register(lambda a: a, name="after", schema={"type": "object"})
        assert len(cli_calls) == 2  # post-start registration re-announces


def test_explicit_root_mode_never_touches_cli(tmp_path):
    cli_calls = []
    node = ComputeNode(agents_root=tmp_path / "agents", cli_runner=cli_calls.append)
    node.register(lambda a: a, name="fn", schema={"type": "object"})
    assert cli_calls == []


def test_end_to_end_through_real_socket(short_tmp, capsys):
    node = ComputeNode(agents_root=short_tmp / "agents")

    @node.register
    def greet(who: str) -> dict:
        return {"hello": who}

    with node:
        code = forward_main([str(node.host_socket), "greet", "world"])
    out, err = capsys.readouterr()
    assert code == 0, err
    assert json.loads(out) == {"hello": "world"}
