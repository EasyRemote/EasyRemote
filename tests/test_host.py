"""Warm host end-to-end: daemon host_stream envelope -> resident function."""

import json
import socket

import pytest

from easyremote._host import HostServer
from easyremote._host.server import HostedFunction
from easyremote.errors import InvalidArgument
from easyremote.schema import derive


@pytest.fixture()
def host(short_tmp):
    server = HostServer(short_tmp / "host.sock")
    with server:
        yield server


def hosted(fn, name=None):
    from easyremote import Context

    return HostedFunction(
        name=name or f"er.{fn.__name__}",
        fn=fn,
        signature=derive(fn, context_type=Context),
    )


def stream_request(host, fn, args, *, caller="", call_id="t"):
    request = {
        "request": {"fn": fn, "args": args, "caller": caller, "call_id": call_id}
    }
    return _socket_frames(host, json.dumps(request))


def _socket_frames(host, line):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(host.socket_path))
        connection.sendall((line + "\n").encode())
        frames = []
        for raw in connection.makefile("r"):
            raw = raw.strip()
            if not raw:
                continue
            frames.append(json.loads(raw))
            if "terminal" in frames[-1] or "error" in frames[-1]:
                break
        return frames


def stream_items(frames):
    return [frame["stream_item"] for frame in frames if "stream_item" in frame]


def test_json_types_arrive_intact(host):
    seen = {}

    def echo(text: str, count: int, opts: dict, ratio: float, on: bool) -> dict:
        seen.update(
            text=type(text),
            count=type(count),
            opts=type(opts),
            ratio=type(ratio),
            on=type(on),
        )
        return {"text": text, "count": count}

    host.add(hosted(echo))
    frames = stream_request(
        host,
        "er.echo",
        {"text": "hello world", "count": 3, "opts": {"k": 1}, "ratio": 1.5, "on": True},
    )

    assert stream_items(frames) == [{"text": "hello world", "count": 3}]
    assert frames[-1]["terminal"]["frames"] == 1
    assert seen == {"text": str, "count": int, "opts": dict, "ratio": float, "on": bool}


def test_optional_parameters_stay_optional(host):
    def greet(who: str, excited: bool = False) -> str:
        return f"{who}{'!' if excited else ''}"

    host.add(hosted(greet))
    frames = stream_request(host, "er.greet", {"who": "easynet"})

    assert stream_items(frames) == ["easynet"]


def test_varargs_do_not_consume_missing_default_leading_param(host):
    def collect(base: int = 10, *nums: int) -> dict:
        return {"base": base, "nums": list(nums)}

    host.add(hosted(collect))
    frames = stream_request(host, "er.collect", {"nums": [1, 2]})

    assert stream_items(frames) == [{"base": 10, "nums": [1, 2]}]


def test_bytes_parameter_is_base64_decoded(host):
    def take(data: bytes) -> int:
        return len(data)

    host.add(hosted(take))
    frames = stream_request(host, "er.take", {"data": "AAEC"})

    assert stream_items(frames) == [3]


def test_async_function_is_awaited(host):
    async def add(a: int, b: int) -> int:
        return a + b

    host.add(hosted(add))
    frames = stream_request(host, "er.add", {"a": 1, "b": 2})

    assert stream_items(frames) == [3]


def test_empty_args_object_means_no_args(host):
    def ping() -> str:
        return "pong"

    host.add(hosted(ping))
    frames = stream_request(host, "er.ping", {})

    assert stream_items(frames) == ["pong"]


def test_missing_function_is_invalid_argument(host):
    frames = stream_request(host, "er.missing", {})

    assert frames == [
        {
            "error": {
                "kind": InvalidArgument.KIND,
                "reason": "not_found",
                "message": "no function 'er.missing' on this node",
            }
        }
    ]


def test_unexpected_keyword_is_invalid_argument(host):
    def one(a: int) -> int:
        return a

    host.add(hosted(one))
    frames = stream_request(host, "er.one", {"a": 1, "b": 2})

    assert frames[0]["error"]["kind"] == InvalidArgument.KIND
    assert frames[0]["error"]["reason"] == "argument_mismatch"


def test_runtime_exception_maps_to_internal(host):
    def boom() -> str:
        raise RuntimeError("kaput")

    host.add(hosted(boom))
    frames = stream_request(host, "er.boom", {})

    assert frames[0]["error"]["kind"] == "INTERNAL"
    assert frames[0]["error"]["reason"] == "function_raised"
    assert "kaput" in frames[0]["error"]["message"]


def test_runtime_type_error_maps_to_internal_not_argument_error(host):
    def boom() -> str:
        raise TypeError("internal bug")

    host.add(hosted(boom))
    frames = stream_request(host, "er.boom", {})

    assert frames[0]["error"]["kind"] == "INTERNAL"
    assert frames[0]["error"]["reason"] == "function_raised"
    assert "internal bug" in frames[0]["error"]["message"]


def test_non_finite_output_is_rejected_before_wire_json(host):
    def bad_number() -> float:
        return float("nan")

    host.add(hosted(bad_number))
    frames = stream_request(host, "er.bad_number", {})

    assert frames[0]["error"]["kind"] == InvalidArgument.KIND
    assert frames[0]["error"]["reason"] == "invalid_json_payload"


def test_invalid_json_is_bad_request(host):
    frames = _socket_frames(host, "{not json")

    assert frames[0]["error"]["kind"] == InvalidArgument.KIND
    assert frames[0]["error"]["reason"] == "bad_request"


def test_malformed_envelope_is_bad_request(host):
    frames = _socket_frames(host, json.dumps({"fn": "er.ping", "args": {}}))

    assert frames[0]["error"]["kind"] == InvalidArgument.KIND
    assert frames[0]["error"]["reason"] == "bad_request"
    assert "request object" in frames[0]["error"]["message"]


def test_falsy_non_object_args_are_rejected(host):
    def ping() -> str:
        return "pong"

    host.add(hosted(ping))
    frames = stream_request(host, "er.ping", [])

    assert frames[0]["error"]["kind"] == InvalidArgument.KIND
    assert frames[0]["error"]["reason"] == "bad_request"
    assert "args must be a JSON object" in frames[0]["error"]["message"]


def test_stop_removes_socket(short_tmp):
    server = HostServer(short_tmp / "host.sock")
    server.start()
    assert server.socket_path.exists()
    assert (server.socket_path.parent.stat().st_mode & 0o777) == 0o700
    assert (server.socket_path.stat().st_mode & 0o777) == 0o600
    server.stop()
    assert not server.socket_path.exists()


def test_too_long_socket_path_fails_actionably(tmp_path):
    deep = tmp_path / ("d" * 120) / "host.sock"
    server = HostServer(deep)
    with pytest.raises(Exception, match="abilities_dir"):
        server.start()


def test_generator_streams_frames_then_terminal(host):
    def generate(prompt: str):
        for tok in ["a", "b", "c"]:
            yield f"{tok}:{prompt}"

    host.add(hosted(generate))
    frames = stream_request(host, "er.generate", {"prompt": "hi"})

    items = [frame for frame in frames if "stream_item" in frame]
    assert [frame["seq"] for frame in items] == [0, 1, 2]
    assert stream_items(frames) == ["a:hi", "b:hi", "c:hi"]
    assert frames[-1]["terminal"]["frames"] == 3
    assert frames[-1]["terminal"]["output_hash"].startswith("sha256:")


def test_unary_context_function_gets_injected_caller(host):
    from easyremote import Context

    def whoami(ctx: Context, q: str) -> dict:
        return {"q": q, "caller": ctx.caller, "inv": ctx.invocation_id}

    host.add(hosted(whoami))
    frames = stream_request(
        host,
        "er.whoami",
        {"q": "hi"},
        caller="easynet:///r/acme/user/alice",
        call_id="inv-1",
    )

    assert stream_items(frames) == [
        {"q": "hi", "caller": "easynet:///r/acme/user/alice", "inv": "inv-1"}
    ]
    assert frames[-1]["terminal"]["frames"] == 1


def test_stream_context_function_reads_caller_each_frame(host):
    from easyremote import Context

    def tagged(ctx: Context, prompt: str):
        for i in range(3):
            yield {"i": i, "by": ctx.caller}

    host.add(hosted(tagged))
    frames = stream_request(
        host,
        "er.tagged",
        {"prompt": "p"},
        caller="easynet:///r/acme/device/bob",
        call_id="inv-2",
    )

    assert stream_items(frames) == [
        {"i": i, "by": "easynet:///r/acme/device/bob"} for i in range(3)
    ]


def test_rolling_hash_matches_daemon_golden_vector():
    # Cross-language contract canary: this digest is computed the same
    # way by the daemon's host_stream_executor::RollingHash
    # (H(prev || seq.to_be_bytes() || compact_sorted_json(frame)),
    # seeded from sha256("")). If this value drifts, the daemon will
    # reject otherwise-valid streams as STREAM_TRUNCATED. Verified
    # byte-identical against a standalone Rust replica using the same
    # sha2 / serde_json versions.
    import easynet_sdk

    writer = easynet_sdk.HostBindingClient(
        easynet_sdk.LocalHostBindingTransport()
    ).open_frame_writer()
    for frame in ["a:hi", "b:hi", "c:hi"]:
        writer.write_item(frame)
    assert (
        writer.output_hash
        == "sha256:653e1bed022d2aa75fba7d09f92bb1d1db86c3caffb89cf54e6f7556ff3e3183"
    )
