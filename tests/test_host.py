"""Warm host end-to-end: daemon host_stream envelope -> resident function."""

import json
import socket

import pytest

from easyremote import StreamFrame
from easyremote._host import HostServer
from easyremote._host.protocol import (
    HEADER,
    MAGIC,
    MAX_PAYLOAD_BYTES,
    FrameKind,
    HostFrame,
    decode_item,
    receive_frame,
    request_frame,
)
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


def stream_request(
    host,
    fn,
    args,
    *,
    caller="easynet:///r/acme/user/test-caller",
    call_id="t",
    parent_receipt=None,
):
    body = {"fn": fn, "args": args, "caller": caller, "call_id": call_id}
    if parent_receipt is not None:
        body["parent_receipt"] = parent_receipt
    request = {"request": body}
    return _socket_frames(host, request)


def _socket_frames(host, request):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(host.socket_path))
        if not isinstance(request, dict):
            connection.sendall(request)
        else:
            connection.sendall(request_frame(request).to_bytes())
        frames = []
        while True:
            frame = receive_frame(connection)
            if frame.kind is FrameKind.ITEM:
                frames.append(
                    {
                        "stream_item": decode_item(frame),
                        "seq": frame.sequence,
                        "content_type": frame.content_type,
                    }
                )
            elif frame.kind is FrameKind.TERMINAL:
                frames.append(
                    {
                        "terminal": {
                            "output_hash": "sha256:" + frame.payload.hex(),
                            "frames": frame.sequence,
                        }
                    }
                )
                break
            elif frame.kind is FrameKind.ERROR:
                frames.append({"error": json.loads(frame.payload)})
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
    frames = _socket_frames(
        host,
        HostFrame(
            FrameKind.REQUEST,
            0,
            content_type="application/json",
            payload=b"{not json",
        ).to_bytes(),
    )

    assert frames[0]["error"]["kind"] == InvalidArgument.KIND
    assert frames[0]["error"]["reason"] == "bad_request"


def test_binary_request_accepts_partial_socket_writes(host):
    def ping() -> str:
        return "pong"

    host.add(hosted(ping))
    raw = request_frame(
        {
            "request": {
                "fn": "er.ping",
                "args": {},
                "caller": "easynet:///r/acme/user/alice",
                "call_id": "partial",
            }
        }
    ).to_bytes()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(host.socket_path))
        for offset in range(0, len(raw), 3):
            connection.sendall(raw[offset : offset + 3])
        item = receive_frame(connection)
        terminal = receive_frame(connection)

    assert decode_item(item) == "pong"
    assert terminal.kind is FrameKind.TERMINAL


def test_binary_request_rejects_unknown_version(host):
    raw = bytearray(request_frame({"request": {}}).to_bytes())
    raw[4] = 99

    frames = _socket_frames(host, bytes(raw))

    assert frames[0]["error"]["kind"] == InvalidArgument.KIND
    assert "version 99" in frames[0]["error"]["message"]


def test_binary_request_rejects_oversized_payload_before_read(host):
    raw = HEADER.pack(
        MAGIC,
        1,
        int(FrameKind.REQUEST),
        0,
        0,
        0,
        MAX_PAYLOAD_BYTES + 1,
    )

    frames = _socket_frames(host, raw)

    assert frames[0]["error"]["kind"] == InvalidArgument.KIND
    assert "payload exceeds protocol limit" in frames[0]["error"]["message"]


def test_malformed_envelope_is_bad_request(host):
    frames = _socket_frames(host, {"fn": "er.ping", "args": {}})

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


def test_ordinary_function_returning_iterator_streams(host):
    from collections.abc import Iterator

    def generate(n: int) -> Iterator[int]:
        return iter(range(n))

    host.add(hosted(generate))

    assert stream_items(stream_request(host, "er.generate", {"n": 3})) == [0, 1, 2]


def test_positional_only_parameters_are_rehydrated_positionally(host):
    def add(left: int, /, right: int = 1) -> int:
        return left + right

    host.add(hosted(add))

    assert stream_items(stream_request(host, "er.add", {"left": 4, "right": 3})) == [7]


def test_multimodal_frames_preserve_raw_bytes_and_media_types(host):
    def media():
        yield StreamFrame(b"\xff\xd8jpeg", "image/jpeg")
        yield StreamFrame(b"opus", "audio/opus")
        yield b"opaque"

    host.add(hosted(media))
    frames = stream_request(host, "er.media", {})

    items = [frame for frame in frames if "stream_item" in frame]
    assert [item["content_type"] for item in items] == [
        "image/jpeg",
        "audio/opus",
        "application/octet-stream",
    ]
    assert [item["stream_item"].payload for item in items] == [
        b"\xff\xd8jpeg",
        b"opus",
        b"opaque",
    ]


def test_async_generator_preserves_typed_media_frames(host):
    async def audio():
        yield StreamFrame(b"opus-1", "audio/opus")
        yield StreamFrame(b"opus-2", "audio/opus")

    host.add(hosted(audio))
    frames = stream_request(host, "er.audio", {})

    assert [item.payload for item in stream_items(frames)] == [b"opus-1", b"opus-2"]


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
        caller="easynet:///r/acme/user/bob",
        call_id="inv-2",
    )

    assert stream_items(frames) == [
        {"i": i, "by": "easynet:///r/acme/user/bob"} for i in range(3)
    ]


def test_context_child_call_uses_parent_receipt_dispatcher(short_tmp, runtime_receipt):
    from easyremote import (
        Context,
        FreshContextChild,
        ResolvedTargetSubject,
    )
    from easyremote._host.server import HostServer

    seen = {}

    class FakeDispatcher:
        def __init__(self, receipt):
            self.receipt = receipt
            self.closed = False

        def call(self, target, /, *args, **kwargs):
            seen["receipt_ura"] = self.receipt.raw["receipt_ura"]
            seen["function"] = target.function
            seen["args"] = args
            seen["kwargs"] = kwargs
            return {
                "child": target.function,
                "receipt": self.receipt.raw["receipt_ura"],
            }

        def invoke(self, function, /, *args, **kwargs):
            raise AssertionError("unexpected invoke")

        def stream(self, function, /, *args, **kwargs):
            raise AssertionError("unexpected stream")

        def close(self):
            seen["closed"] = True
            self.closed = True

    def factory(receipt):
        assert receipt is not None
        return FakeDispatcher(receipt)

    def parent(ctx: Context, q: str):
        return ctx.call(
            Context.target(
                "er.child",
                invocation_policy=FreshContextChild(ResolvedTargetSubject()),
            ),
            q=q,
        )

    parent_receipt = runtime_receipt(
        invocation_id="inv-parent-1",
        receipt_type="completed",
        state="Completed",
        receipt_ura="easynet:///r/example/resource/agent.easyremote.test/invocation/parent-1/receipt",
        cleanup_complete=True,
    )

    with HostServer(
        short_tmp / "host.sock", context_dispatcher_factory=factory
    ) as server:
        server.add(hosted(parent))
        frames = stream_request(
            server,
            "er.parent",
            {"q": "hi"},
            call_id="inv-parent-1",
            parent_receipt=parent_receipt,
        )

    assert stream_items(frames) == [
        {
            "child": "er.child",
            "receipt": "easynet:///r/example/resource/agent.easyremote.test/invocation/parent-1/receipt",
        }
    ]
    assert seen == {
        "receipt_ura": "easynet:///r/example/resource/agent.easyremote.test/invocation/parent-1/receipt",
        "function": "er.child",
        "args": (),
        "kwargs": {"q": "hi"},
        "closed": True,
    }


def test_rolling_hash_matches_daemon_golden_vector():
    # Cross-language contract canary: this digest is computed the same
    # way by the daemon's host_stream_executor::RollingHash
    # (H(prev || seq.to_be_bytes() || compact_sorted_json(frame)),
    # seeded from sha256("")). If this value drifts, the daemon will
    # reject otherwise-valid streams as STREAM_TRUNCATED. Verified
    # byte-identical against a standalone Rust replica using the same
    # sha2 / serde_json versions.
    from easyremote._host.protocol import FrameWriter

    writer = FrameWriter()
    for frame in ["a:hi", "b:hi", "c:hi"]:
        writer.write_item(frame)
    assert (
        writer.output_hash
        == "sha256:4b454f7a5008aa83decbe76c9da3f3b3ea891371448dccde2de908fbf48e9f93"
    )


def test_unary_bytes_return_uses_json_base64_contract(host):
    def thumbnail(image: bytes, size: int) -> bytes:
        return image[:size]

    host.add(hosted(thumbnail))
    frames = stream_request(host, "er.thumbnail", {"image": "AAEC", "size": 2})
    assert stream_items(frames) == ["AAE="]
    assert frames[0]["content_type"] == "application/json"
