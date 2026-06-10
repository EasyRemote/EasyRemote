"""Per-invocation forwarder: the stdin/stdout shim between daemon and warm host.

The device-ability runtime invokes ``command`` with the args JSON on
stdin and reads the result JSON from stdout (contract documented in the
``easynet ability new`` scaffold). This shim relays stdin to the
resident :class:`~easyremote._host.HostServer` over its Unix socket and
prints the host's result — JSON types arrive intact, no re-typing
anywhere. Exit 0 with the result on stdout; exit 1 with the error on
stderr (surfaced to the caller by the runtime).

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
    if len(argv) != 2:
        print(
            "usage: python -m easyremote._host.forward <socket> <fn>  (args on stdin)",
            file=sys.stderr,
        )
        return 1
    socket_path, fn_name = argv

    stdin_payload = sys.stdin.read().strip()
    try:
        args = json.loads(stdin_payload) if stdin_payload else {}
    except json.JSONDecodeError as exc:
        print(f"stdin is not valid JSON: {exc}", file=sys.stderr)
        return 1

    request = json.dumps({"fn": fn_name, "args": args}, separators=(",", ":"))
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
