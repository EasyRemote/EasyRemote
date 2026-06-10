"""Warm host end-to-end: forwarder → UDS → resident function → stdout.

Exercises the real socket path the daemon's shell executor will use,
minus the daemon itself (that is #11's integration suite).
"""

import json

import pytest

from easyremote._host import HostServer
from easyremote._host.forward import main as forward_main
from easyremote._host.server import HostedFunction
from easyremote.schema import derive


@pytest.fixture()
def host(short_tmp):
    server = HostServer(short_tmp / "host.sock")
    with server:
        yield server


def hosted(fn, name=None):
    return HostedFunction(name=name or fn.__name__, fn=fn, signature=derive(fn))


def run_forward(host, fn_name, *values, capsys=None):
    code = forward_main([str(host.socket_path), fn_name, *values])
    out, err = capsys.readouterr()
    return code, out, err


def test_rendered_values_are_retyped_by_schema(host, capsys):
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
    # Values exactly as template.rs renders them: strings bare, the
    # rest JSON-encoded.
    code, out, err = run_forward(
        host, "echo", "hello world", "3", '{"k":1}', "1.5", "true", capsys=capsys
    )
    assert code == 0, err
    assert json.loads(out) == {"text": "hello world", "count": 3}
    assert seen == {"text": str, "count": int, "opts": dict, "ratio": float, "on": bool}


def test_bytes_parameter_is_base64_decoded(host, capsys):
    def take(data: bytes) -> int:
        return len(data)

    host.add(hosted(take))
    code, out, _ = run_forward(host, "take", "AAEC", capsys=capsys)  # b64 of 00 01 02
    assert code == 0
    assert json.loads(out) == 3


def test_async_function_is_awaited(host, capsys):
    async def add(a: int, b: int) -> int:
        return a + b

    host.add(hosted(add))
    code, out, _ = run_forward(host, "add", "1", "2", capsys=capsys)
    assert code == 0
    assert json.loads(out) == 3


def test_unknown_function_fails_with_not_found(host, capsys):
    code, _, err = run_forward(host, "nope", capsys=capsys)
    assert code == 1
    assert "not_found" in err


def test_function_exception_maps_to_internal(host, capsys):
    def boom() -> str:
        raise RuntimeError("kaput")

    host.add(hosted(boom))
    code, _, err = run_forward(host, "boom", capsys=capsys)
    assert code == 1
    assert "INTERNAL/function_raised" in err
    assert "kaput" in err


def test_arity_mismatch_is_invalid_argument(host, capsys):
    def one(a: int) -> int:
        return a

    host.add(hosted(one))
    code, _, err = run_forward(host, "one", "1", "2", capsys=capsys)
    assert code == 1
    assert "INVALID_ARGUMENT" in err


def test_unreachable_host_is_actionable(short_tmp, capsys):
    code = forward_main([str(short_tmp / "absent.sock"), "fn"])
    _, err = capsys.readouterr()
    assert code == 1
    assert "ComputeNode process running" in err


def test_stop_removes_socket(short_tmp):
    server = HostServer(short_tmp / "host.sock")
    server.start()
    assert server.socket_path.exists()
    server.stop()
    assert not server.socket_path.exists()


def test_too_long_socket_path_fails_actionably(tmp_path):
    deep = tmp_path / ("d" * 120) / "host.sock"
    server = HostServer(deep)
    with pytest.raises(Exception, match="agents_root"):
        server.start()
