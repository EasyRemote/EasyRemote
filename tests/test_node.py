"""ComputeNode: device-ability packaging, deploy announcements, lifecycle."""

import io
import json
from collections.abc import Iterator

import pytest

from easyremote._host.forward import main as forward_main
from easyremote.context import Context
from easyremote.errors import InvalidArgument, Unavailable
from easyremote.node import ComputeNode


@pytest.fixture()
def node(tmp_path):
    deploys = []
    node = ComputeNode(abilities_dir=tmp_path / "abilities", cli_runner=deploys.append)
    node.deploys = deploys
    return node


def read_manifest(info):
    return json.loads((info.package_dir / "ability.json").read_text())


def test_register_writes_scaffold_shaped_ability_json(node, monkeypatch):
    monkeypatch.setenv("EASYREMOTE_FORWARDER", "python")  # deterministic command

    @node.register
    def ai_inference(prompt: str, max_tokens: int = 64) -> str:
        """Generate a completion on this device."""
        return prompt

    manifest = read_manifest(ai_inference.info)
    assert manifest["name"] == "er.ai_inference"
    assert manifest["tool_name"] == "er.ai_inference"
    assert manifest["description"] == "Generate a completion on this device."
    assert manifest["category"] == "easyremote"

    # stdin contract: no argv templates, no required-all rewriting —
    # optionals keep their true schema semantics.
    schema = manifest["input_schema"]
    assert schema["required"] == ["prompt"]
    assert schema["properties"]["max_tokens"]["default"] == 64
    assert manifest["output_schema"] == {"type": "string"}

    command = manifest["command"]
    assert "-m easyremote._host.forward" in command
    assert command.endswith("er.ai_inference")
    assert "{{" not in command  # the argv-template era is over


def test_device_ontology_naming_unpaired(node, monkeypatch):
    import easyremote.config as config

    monkeypatch.setattr(config, "_settings", None)
    monkeypatch.setenv("EASYNET_CREDENTIALS", "/nonexistent/credentials.json")

    @node.register
    def fn(a: int) -> int:
        return a

    assert fn.qualified_name == "er.fn"
    assert fn.info.package_dir.name == "er.fn"
    assert fn.info.ura is None  # unpaired: absent, never invented


def test_device_ontology_naming_paired(tmp_path, monkeypatch):
    import easyremote.config as config

    monkeypatch.setattr(config, "_settings", None)
    credentials = tmp_path / "credentials.json"
    credentials.write_text(
        json.dumps({"realm": "acme", "node_id": "dev-a", "hub_endpoint": "h:443"})
    )
    monkeypatch.setenv("EASYNET_CREDENTIALS", str(credentials))
    node = ComputeNode(abilities_dir=tmp_path / "abilities", cli_runner=lambda _: None)

    @node.register
    def fn(a: int) -> int:
        return a

    # The canonical device-ability shape (RFC-001; `easynet ability
    # invoke` documents the same form).
    assert fn.info.ura == "easynet:///r/acme/ability/device.dev-a.er.fn"


def test_nothing_deploys_before_start(node):
    @node.register
    def fn(a: int) -> int:
        return a

    assert node.deploys == []


def test_start_deploys_each_package_to_local_node(short_tmp):
    deploys = []
    node = ComputeNode(abilities_dir=short_tmp / "abilities", cli_runner=deploys.append)

    @node.register
    def fn(a: int) -> int:
        return a

    with node:
        assert deploys == [
            ["ability", "deploy", str(fn.info.package_dir), "--node", "local"]
        ]

        @node.register
        def late(b: int) -> int:
            return b

        assert len(deploys) == 2  # post-start registration publishes immediately


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
        ComputeNode(namespace="er.bad", abilities_dir=tmp_path)


def test_registered_function_still_callable_locally(node):
    @node.register
    def double(x: int) -> int:
        return x * 2

    assert double(21) == 42


def test_gateway_param_accepted_classic_shape(tmp_path):
    # Classic FaaS shape: ComputeNode("hub:8443"). Unpaired test env →
    # no credentials to validate against, so it is simply carried.
    node = ComputeNode("hub.example:8443", abilities_dir=tmp_path / "a")
    assert node.namespace == "er"


def test_end_to_end_through_real_socket(short_tmp, capsys, monkeypatch):
    node = ComputeNode(abilities_dir=short_tmp / "abilities", cli_runner=lambda _: None)

    @node.register
    def greet(who: str, excited: bool = False) -> dict:
        return {"hello": who, "excited": excited}

    with node:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"who": "world"})))
        code = forward_main([str(node.host_socket), "er.greet"])
    out, err = capsys.readouterr()
    assert code == 0, err
    assert json.loads(out) == {"hello": "world", "excited": False}
