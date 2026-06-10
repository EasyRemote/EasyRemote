#!/usr/bin/env python3
"""Forwarder latency bench — runnable without a daemon.

Measures the full per-invocation transport floor the daemon pays to
reach a warm function: spawn forwarder → stdin args → UDS → resident
function → stdout result. Compares the Python shim against the
lazily-compiled C fast forwarder (SPEC D2 interim; host-attach,
Cli PR-1, removes the spawn entirely).
"""

import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from easyremote._host import HostServer, fastpath
from easyremote._host.server import HostedFunction
from easyremote.schema import derive


def add_numbers(a: int, b: int) -> int:
    return a + b


def bench(command: list[str], rounds: int = 30) -> list[float]:
    samples = []
    payload = json.dumps({"a": 1, "b": 2})
    for _ in range(rounds):
        started = time.perf_counter()
        done = subprocess.run(
            command, input=payload, capture_output=True, text=True, timeout=10
        )
        assert done.returncode == 0, done.stderr
        samples.append((time.perf_counter() - started) * 1000)
    return samples


def report(label: str, samples: list[float]) -> None:
    print(
        f"  {label:<18} p50 {statistics.median(samples):6.1f}ms"
        f"   p95 {sorted(samples)[int(len(samples) * 0.95) - 1]:6.1f}ms"
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="er-", dir="/tmp") as tmp:
        server = HostServer(Path(tmp) / "host.sock")
        server.add(
            HostedFunction(name="er.add", fn=add_numbers, signature=derive(add_numbers))
        )
        with server:
            python_cmd = [
                sys.executable,
                "-m",
                "easyremote._host.forward",
                str(server.socket_path),
                "er.add",
            ]
            print("per-invocation transport floor (spawn → UDS → result):")
            report("python shim", bench(python_cmd))

            native = fastpath.forwarder_command(server.socket_path, "er.add")
            if "-m easyremote._host.forward" in native:
                print("  native forwarder   (no C compiler found — skipped)")
            else:
                report("native forwarder", bench(native.split(" ")))


if __name__ == "__main__":
    main()
