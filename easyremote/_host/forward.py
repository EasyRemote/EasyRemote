"""Per-invocation forwarder: the argv shim between daemon and warm host.

Spawned by the daemon's shell executor as
``python -m easyremote._host.forward <socket> <fn> [value ...]``.
It knows nothing about types — it relays the rendered values verbatim
and prints the host's result JSON to stdout (the executor's
``utf8_trim`` contract). Exit 0 with the result on stdout; exit 1 with
the error on stderr (the executor folds stderr into its failure
message).

This shim is the transition cost of SPEC §4.1 D2: one interpreter
spawn per call until the daemon host-attach protocol (Cli PR-1)
removes it.
"""

from __future__ import annotations

import json
import socket
import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        print(
            "usage: python -m easyremote._host.forward <socket> <fn> [value ...]",
            file=sys.stderr,
        )
        return 1
    socket_path, fn_name, *values = argv

    request = json.dumps({"fn": fn_name, "values": values}, separators=(",", ":"))
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(socket_path)
            connection.sendall(request.encode("utf-8") + b"\n")
            response = _read_line(connection)
    except OSError as exc:
        print(
            f"easyremote host unreachable at {socket_path}: {exc}"
            " — is the ComputeNode process running?",
            file=sys.stderr,
        )
        return 1

    try:
        payload = json.loads(response)
    except json.JSONDecodeError as exc:
        print(f"easyremote host sent invalid JSON: {exc}", file=sys.stderr)
        return 1

    if payload.get("ok"):
        sys.stdout.write(json.dumps(payload.get("result"), separators=(",", ":")))
        return 0
    error = payload.get("error", {})
    print(
        f"{error.get('kind', 'INTERNAL')}/{error.get('reason', '')}:"
        f" {error.get('message', '')}",
        file=sys.stderr,
    )
    return 1


def _read_line(connection: socket.socket) -> str:
    chunks: list[bytes] = []
    while True:
        chunk = connection.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
        if chunk.endswith(b"\n"):
            break
    return b"".join(chunks).decode("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
