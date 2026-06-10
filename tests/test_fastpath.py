"""The C fast forwarder: compilation, end-to-end parity, wire-prefix pin."""

import json
import shutil
import subprocess

import pytest

from easyremote._host import HostServer, fastpath
from easyremote._host.server import HostedFunction, _error_response
from easyremote.schema import derive

HAS_CC = any(shutil.which(c) for c in ("cc", "clang", "gcc"))
needs_cc = pytest.mark.skipif(not HAS_CC, reason="no C compiler on PATH")


def test_wire_prefixes_are_pinned_for_the_c_forwarder():
    """forward.c slices responses by exact prefix — pin the host bytes."""
    ok = json.dumps({"ok": True, "result": {"x": 1}}, separators=(",", ":"))
    assert ok.startswith('{"ok":true,"result":')
    err = json.dumps(_error_response("INTERNAL", "r", "m"), separators=(",", ":"))
    assert err.startswith('{"ok":false,"error":')


def test_python_fallback_is_forced_by_env(short_tmp, monkeypatch):
    monkeypatch.setenv("EASYREMOTE_FORWARDER", "python")
    command = fastpath.forwarder_command(short_tmp / "s.sock", "er.fn")
    assert "-m easyremote._host.forward" in command


@needs_cc
def test_native_forwarder_compiles_and_round_trips(short_tmp, monkeypatch):
    monkeypatch.delenv("EASYREMOTE_FORWARDER", raising=False)

    def greet(who: str, excited: bool = False) -> dict:
        return {"hello": who, "excited": excited}

    server = HostServer(short_tmp / "host.sock")
    server.add(HostedFunction(name="er.greet", fn=greet, signature=derive(greet)))
    with server:
        command = fastpath.forwarder_command(server.socket_path, "er.greet")
        assert "-m easyremote._host.forward" not in command  # native path chosen

        binary, socket_path, fn = command.split(" ")
        done = subprocess.run(
            [binary, socket_path, fn],
            input=json.dumps({"who": "world"}),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert done.returncode == 0, done.stderr
        assert json.loads(done.stdout) == {"hello": "world", "excited": False}

        # error path: unknown function → error JSON on stderr, exit 1
        bad = subprocess.run(
            [binary, socket_path, "er.nope"],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert bad.returncode == 1
        assert "not_found" in bad.stderr
