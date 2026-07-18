"""ComputeNode: device-ability packaging, deploy announcements, lifecycle."""

import json
import socket
from collections.abc import Iterator
from functools import partial

import pytest

from easyremote.context import Context
from easyremote.errors import InvalidArgument, Unavailable
from easyremote.identity import LocalIdentity
from easyremote.node import ComputeNode


@pytest.fixture()
def node(tmp_path):
    installer = FakeAbilityControl()
    node = ComputeNode(
        abilities_dir=tmp_path / "abilities",
        ability_control=installer,
        runtime_provider=ReadyRuntimeProvider(),
    )
    node.installer = installer
    return node


class FakeAbilityControl:
    def __init__(self):
        self.installs = []
        self.fail = None

    def install(self, path, *, node):
        self.installs.append((path, node))
        if self.fail is not None:
            raise self.fail


class ReadyRuntime:
    identity = LocalIdentity(
        realm="acme",
        node_id="dev-a",
        username=None,
        hub_endpoint="hub:443",
    )

    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class ReadyRuntimeProvider:
    def __init__(self):
        self.connections = []

    def connect(self):
        connection = ReadyRuntime()
        self.connections.append(connection)
        return connection


class OnboardingRuntimeProvider:
    def connect(self):
        raise Unavailable("Pair with `easynet pair`", reason="onboarding_required")


def read_manifest(info):
    return json.loads((info.package_dir / "ability.json").read_text())


def host_stream_frames(socket_path, fn, args):
    request = {
        "request": {
            "fn": fn,
            "args": args,
            "caller": "easynet:///r/acme/device/test-caller",
            "call_id": "t",
        }
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(socket_path))
        connection.sendall((json.dumps(request) + "\n").encode())
        frames = []
        for raw in connection.makefile("r"):
            raw = raw.strip()
            if not raw:
                continue
            frames.append(json.loads(raw))
            if "terminal" in frames[-1] or "error" in frames[-1]:
                break
        return frames


def test_register_writes_scaffold_shaped_ability_json(node):
    @node.register
    def ai_inference(prompt: str, max_tokens: int = 64) -> str:
        """Generate a completion on this device."""
        return prompt

    manifest = read_manifest(ai_inference.info)
    # Canonical shape for the daemon's install transaction: name is the
    # verb only (AbilityManifest.name forbids dots); namespace carries
    # `er` separately; tool_name keeps the qualified human-facing form.
    assert manifest["name"] == "ai_inference"
    assert manifest["namespace"] == "er"
    assert manifest["tool_name"] == "er.ai_inference"
    assert manifest["description"] == "Generate a completion on this device."
    assert manifest["category"] == "easyremote"

    # stdin contract: no argv templates, no required-all rewriting —
    # optionals keep their true schema semantics.
    schema = manifest["input_schema"]
    assert schema["required"] == ["prompt"]
    assert schema["properties"]["max_tokens"]["default"] == 64
    assert manifest["output_schema"] == {"type": "string"}

    # EVERY ability — unary or generator — routes through the host_stream
    # executor: it carries full JSON args + caller identity in the request
    # frame (the shell executor nulls stdin and only templates argv, so it
    # cannot pass arbitrary args). A unary function's single return value
    # rides back as one terminal frame.
    exec_ = manifest["exec"]
    assert exec_["kind"] == "host_stream"
    assert exec_["function"] == "er.ai_inference"
    assert exec_["host_socket"].endswith("host.sock")
    assert "command" not in manifest  # the daemon never read `command`


def test_non_finite_defaults_are_not_written_to_ability_json(node):
    @node.register
    def score(value: float = float("nan")) -> float:
        return value

    text = (score.info.package_dir / "ability.json").read_text()
    assert "NaN" not in text
    manifest = read_manifest(score.info)
    assert "default" not in manifest["input_schema"]["properties"]["value"]


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
        json.dumps({"realm": "acme", "device_id": "dev-a", "hub_endpoint": "h:443"})
    )
    monkeypatch.setenv("EASYNET_CREDENTIALS", str(credentials))
    node = ComputeNode(
        abilities_dir=tmp_path / "abilities", ability_control=FakeAbilityControl()
    )

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

    assert node.installer.installs == []


def test_start_deploys_each_package_to_local_node(short_tmp):
    installer = FakeAbilityControl()
    provider = ReadyRuntimeProvider()
    node = ComputeNode(
        abilities_dir=short_tmp / "abilities",
        ability_control=installer,
        runtime_provider=provider,
    )

    @node.register
    def fn(a: int) -> int:
        return a

    with node:
        assert installer.installs == [(fn.info.package_dir, "local")]

        @node.register
        def late(b: int) -> int:
            return b

        assert len(installer.installs) == 2
        assert not provider.connections[0].closed
    assert provider.connections[0].closed


def test_serve_prints_actionable_onboarding_without_runtime_trace(tmp_path, capsys):
    node = ComputeNode(
        abilities_dir=tmp_path / "abilities",
        ability_control=FakeAbilityControl(),
        runtime_provider=OnboardingRuntimeProvider(),
    )

    node.serve()

    assert "easynet pair" in capsys.readouterr().out


def test_start_rolls_back_host_when_deploy_fails(short_tmp):
    installer = FakeAbilityControl()
    installer.fail = RuntimeError("deploy failed")
    provider = ReadyRuntimeProvider()
    node = ComputeNode(
        abilities_dir=short_tmp / "abilities",
        ability_control=installer,
        runtime_provider=provider,
    )

    @node.register
    def fn(a: int) -> int:
        return a

    with pytest.raises(RuntimeError, match="deploy failed"):
        node.start()

    assert not node.host_socket.exists()
    assert not node._started
    assert provider.connections[0].closed


def test_post_start_registration_rolls_back_when_deploy_fails(short_tmp):
    installer = FakeAbilityControl()
    node = ComputeNode(
        abilities_dir=short_tmp / "abilities",
        ability_control=installer,
        runtime_provider=ReadyRuntimeProvider(),
    )

    @node.register
    def first(a: int) -> int:
        return a

    with node:
        installer.fail = RuntimeError("late deploy failed")
        with pytest.raises(RuntimeError, match="late deploy failed"):

            @node.register
            def late(b: int) -> int:
                return b

        assert [ability.name for ability in node.abilities] == ["first"]
        frames = host_stream_frames(node.host_socket, "er.late", {"b": 1})
        assert frames[0]["error"]["reason"] == "not_found"


def test_stream_function_writes_host_stream_exec(node):
    # Generators are now supported: they register as server-stream
    # abilities whose manifest declares the `host_stream` executor so
    # the daemon's install transaction binds them stream-mode.
    def chunks(n: int) -> Iterator[str]:
        yield "x"

    fn = node.register(chunks)
    manifest = read_manifest(fn.info)
    assert manifest["name"] == "chunks"
    assert manifest["namespace"] == "er"
    exec_ = manifest["exec"]
    assert exec_["kind"] == "host_stream"
    assert exec_["function"] == "er.chunks"
    assert exec_["host_socket"].endswith("host.sock")


def test_context_function_registers_via_host_stream(node):
    # Context-taking functions are now supported: they route through the
    # host_stream exec (the only path that carries caller identity), so
    # the host can build the injected Context.
    def report(ctx: Context, q: str) -> str:
        return q

    fn = node.register(report)
    manifest = read_manifest(fn.info)
    assert manifest["name"] == "report"
    assert manifest["exec"]["kind"] == "host_stream"
    # `ctx` is the injected first param — it must NOT appear in the
    # caller-facing input schema.
    assert "ctx" not in manifest["input_schema"]["properties"]
    assert list(manifest["input_schema"]["properties"]) == ["q"]


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


def test_default_storage_uses_configured_easynet_process_root(tmp_path, monkeypatch):
    import easyremote.config as config

    monkeypatch.setattr(config, "_settings", None)
    control = tmp_path / "control.json"
    config.configure(control=control)

    node = ComputeNode(ability_control=FakeAbilityControl())

    assert node._abilities_dir == tmp_path / "easyremote" / "abilities"
    assert node.host_socket == tmp_path / "easyremote" / "host.sock"


def test_registered_function_still_callable_locally(node):
    @node.register
    def double(x: int) -> int:
        return x * 2

    assert double(21) == 42


def test_partial_without_name_gets_stable_generated_ability_name(node):
    def add(a: int, b: int) -> int:
        return a + b

    registered = node.register(partial(add, 1))
    assert registered.name.startswith("fn_")
    assert registered.qualified_name == f"er.{registered.name}"


def test_gateway_param_accepted_classic_shape(tmp_path):
    # Classic FaaS shape: ComputeNode("hub:8443"). Unpaired test env →
    # no credentials to validate against, so it is simply carried.
    node = ComputeNode("hub.example:8443", abilities_dir=tmp_path / "a")
    assert node.namespace == "er"


def test_end_to_end_through_real_socket(short_tmp):
    node = ComputeNode(
        abilities_dir=short_tmp / "abilities",
        ability_control=FakeAbilityControl(),
        runtime_provider=ReadyRuntimeProvider(),
    )

    @node.register
    def greet(who: str, excited: bool = False) -> dict:
        return {"hello": who, "excited": excited}

    with node:
        frames = host_stream_frames(node.host_socket, "er.greet", {"who": "world"})

    items = [frame["stream_item"] for frame in frames if "stream_item" in frame]
    assert items == [{"hello": "world", "excited": False}]
    assert frames[-1]["terminal"]["frames"] == 1
