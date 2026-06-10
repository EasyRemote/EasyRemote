"""Warm host end-to-end: stdin → forwarder → UDS → resident function → stdout.

Exercises the real device-ability transport (args JSON on stdin,
result JSON on stdout) minus the daemon itself (integration covers that).
"""

import io
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


def run_forward(host, fn_name, args, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(args)))
    code = forward_main([str(host.socket_path), fn_name])
    out, err = capsys.readouterr()
    return code, out, err


def test_json_types_arrive_intact(host, capsys, monkeypatch):
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
    code, out, err = run_forward(
        host,
        "echo",
        {"text": "hello world", "count": 3, "opts": {"k": 1}, "ratio": 1.5, "on": True},
        capsys,
        monkeypatch,
    )
    assert code == 0, err
    assert json.loads(out) == {"text": "hello world", "count": 3}
    assert seen == {"text": str, "count": int, "opts": dict, "ratio": float, "on": bool}


def test_optional_parameters_stay_optional(host, capsys, monkeypatch):
    def greet(who: str, excited: bool = False) -> str:
        return f"{who}{'!' if excited else ''}"

    host.add(hosted(greet))
    code, out, _ = run_forward(host, "greet", {"who": "easynet"}, capsys, monkeypatch)
    assert code == 0
    assert json.loads(out) == "easynet"  # default applied by the function itself


def test_bytes_parameter_is_base64_decoded(host, capsys, monkeypatch):
    def take(data: bytes) -> int:
        return len(data)

    host.add(hosted(take))
    code, out, _ = run_forward(host, "take", {"data": "AAEC"}, capsys, monkeypatch)
    assert code == 0
    assert json.loads(out) == 3


def test_async_function_is_awaited(host, capsys, monkeypatch):
    async def add(a: int, b: int) -> int:
        return a + b

    host.add(hosted(add))
    code, out, _ = run_forward(host, "add", {"a": 1, "b": 2}, capsys, monkeypatch)
    assert code == 0
    assert json.loads(out) == 3


def test_empty_stdin_means_no_args(host, capsys, monkeypatch):
    def ping() -> str:
        return "pong"

    host.add(hosted(ping))
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    code = forward_main([str(host.socket_path), "ping"])
    out, _ = capsys.readouterr()
    assert code == 0
    assert json.loads(out) == "pong"


def test_unknown_function_fails_with_not_found(host, capsys, monkeypatch):
    code, _, err = run_forward(host, "nope", {}, capsys, monkeypatch)
    assert code == 1
    assert "not_found" in err


def test_unexpected_keyword_is_invalid_argument(host, capsys, monkeypatch):
    def one(a: int) -> int:
        return a

    host.add(hosted(one))
    code, _, err = run_forward(host, "one", {"a": 1, "b": 2}, capsys, monkeypatch)
    assert code == 1
    assert "INVALID_ARGUMENT/argument_mismatch" in err


def test_function_exception_maps_to_internal(host, capsys, monkeypatch):
    def boom() -> str:
        raise RuntimeError("kaput")

    host.add(hosted(boom))
    code, _, err = run_forward(host, "boom", {}, capsys, monkeypatch)
    assert code == 1
    assert "INTERNAL/function_raised" in err
    assert "kaput" in err


def test_invalid_stdin_json_is_reported(host, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))
    code = forward_main([str(host.socket_path), "fn"])
    _, err = capsys.readouterr()
    assert code == 1
    assert "stdin is not valid JSON" in err


def test_unreachable_host_is_actionable(short_tmp, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
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
    with pytest.raises(Exception, match="abilities_dir"):
        server.start()
