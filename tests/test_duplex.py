"""Actual host sockets: incremental media, input half-close and terminal errors."""

import json
import socket
from contextlib import contextmanager

import pytest

from easyremote import Duplex, StreamFrame
from easyremote._host import HostServer
from easyremote._host.protocol import (
    FrameKind,
    HostFrame,
    decode_item,
    receive_frame,
    request_frame,
)
from easyremote._host.server import HostedFunction
from easyremote.schema import derive


@contextmanager
def connected(short_tmp, fn):
    with HostServer(short_tmp / "duplex.sock") as server:
        server.add(HostedFunction("er.echo", fn, derive(fn)))
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(3)
            connection.connect(str(server.socket_path))
            connection.sendall(
                request_frame(
                    {
                        "request": {
                            "fn": "er.echo",
                            "args": {},
                            "call_id": "duplex-1",
                            "caller": "easynet:///r/acme/user/test-caller",
                        }
                    }
                ).to_bytes()
            )
            yield connection


def echo(channel: Duplex) -> None:
    count = 0
    for item in channel:
        channel.send(item)
        count += 1
    channel.send({"frames_received": count})


async def async_echo(channel: Duplex) -> None:
    async for item in channel:
        await channel.asend(item)
    await channel.asend({"frames_received": 1})


@pytest.mark.parametrize("fn", [echo, async_echo])
def test_media_reply_before_input_half_close(short_tmp, fn):
    with connected(short_tmp, fn) as connection:
        payload = b"\x00\xffaudio\x00"
        connection.sendall(
            HostFrame(FrameKind.ITEM, 0, "audio/pcm", payload).to_bytes()
        )
        # This read precedes HALF_CLOSE: batching input until EOF deadlocks/fails.
        frame = receive_frame(connection)
        assert decode_item(frame) == StreamFrame(payload, "audio/pcm")
        connection.sendall(HostFrame(FrameKind.HALF_CLOSE, 1).to_bytes())
        assert decode_item(receive_frame(connection)) == {"frames_received": 1}
        terminal = receive_frame(connection)
        assert terminal.kind is FrameKind.TERMINAL
        assert terminal.sequence == 2


def test_empty_upload_still_returns_final_result(short_tmp):
    with connected(short_tmp, echo) as connection:
        connection.sendall(HostFrame(FrameKind.HALF_CLOSE, 0).to_bytes())
        assert decode_item(receive_frame(connection)) == {"frames_received": 0}
        assert receive_frame(connection).kind is FrameKind.TERMINAL


def test_input_sequence_gap_is_error_not_success(short_tmp):
    with connected(short_tmp, echo) as connection:
        connection.sendall(
            HostFrame(FrameKind.ITEM, 2, "application/json", b"{}").to_bytes()
        )
        frame = receive_frame(connection)
        assert frame.kind is FrameKind.ERROR
        assert json.loads(frame.payload)["reason"] == "stream_truncated"


def test_upload_eof_is_not_half_close(short_tmp):
    with connected(short_tmp, echo) as connection:
        connection.shutdown(socket.SHUT_WR)
        assert receive_frame(connection).kind is FrameKind.ERROR


def test_schema_hides_injected_duplex():
    signature = derive(echo)
    assert signature.duplex_parameter == "channel"
    assert signature.input_schema["properties"] == {}


def test_client_media_and_half_close_delegate_to_sdk():
    from easynet_sdk import BidiSessionAdapter

    from easyremote import BidiSession

    class Channel:
        def __init__(self):
            self.sent = []
            self.closed = False

        def send(self, frame):
            self.sent.append(frame)

        def close_send(self):
            return {"state": "half_closed_local", "terminal": False}

        def recv(self, timeout=None):
            return {"terminal": True, "terminal_receipt": {"verified": True}}

        def close(self):
            self.closed = True

    channel = Channel()
    session = BidiSession(BidiSessionAdapter(channel))
    session.send_frame(StreamFrame(b"\x00\xff", "audio/pcm"), sequence=1)
    assert channel.sent[0]["payload_base64"] == "AP8="
    assert session.close_send()["state"] == "half_closed_local"
    assert not channel.closed
    assert session.recv()["terminal"]


def test_provider_connection_limit_and_stop_unblock_readers(short_tmp):
    from contextlib import ExitStack

    def hold(channel: Duplex) -> None:
        channel.send({"ready": True})
        for _ in channel:
            pass

    with ExitStack() as stack:
        server = stack.enter_context(HostServer(short_tmp / "bound.sock"))
        server.add(HostedFunction("er.hold", hold, derive(hold)))
        peers = []
        for _ in range(32):
            peer = stack.enter_context(
                socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            )
            peer.settimeout(3)
            peer.connect(str(server.socket_path))
            peer.sendall(
                request_frame(
                    {
                        "request": {
                            "fn": "er.hold",
                            "args": {},
                            "call_id": "held",
                            "caller": "easynet:///r/acme/user/test-caller",
                        }
                    }
                ).to_bytes()
            )
            assert decode_item(receive_frame(peer)) == {"ready": True}
            peers.append(peer)
        extra = stack.enter_context(socket.socket(socket.AF_UNIX, socket.SOCK_STREAM))
        extra.settimeout(3)
        extra.connect(str(server.socket_path))
        refusal = receive_frame(extra)
        assert refusal.kind is FrameKind.ERROR
        assert json.loads(refusal.payload)["kind"] == "RESOURCE_EXHAUSTED"
        accept_thread = server._accept_thread
        server.stop()
        assert not accept_thread.is_alive()
        for peer in peers:
            assert peer.recv(1) == b""
