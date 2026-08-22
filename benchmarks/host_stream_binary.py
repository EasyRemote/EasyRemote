"""Reproducible EasyRemote resident-host binary stream benchmark.

Measures the provider-side Python -> Unix socket boundary only. It is not an
end-to-end network SLO and prints its scope explicitly in machine-readable JSON.
"""

from __future__ import annotations

import argparse
import json
import socket
import statistics
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

from easyremote import Context, StreamFrame
from easyremote._host import HostServer
from easyremote._host.protocol import FrameKind, receive_frame, request_frame
from easyremote._host.server import HostedFunction
from easyremote.schema import derive


def payloads(count: int, size: int) -> Iterator[StreamFrame]:
    payload = bytes(size)
    for _ in range(count):
        yield StreamFrame(payload, "application/octet-stream")


def run_once(socket_path: Path, count: int, size: int) -> tuple[float, float]:
    envelope = {
        "request": {
            "fn": "er.payloads",
            "args": {"count": count, "size": size},
            "caller": "easynet:///r/benchmark/user/local",
            "call_id": "benchmark",
        }
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(socket_path))
        started = time.perf_counter_ns()
        connection.sendall(request_frame(envelope).to_bytes())
        first = receive_frame(connection)
        first_seen = time.perf_counter_ns()
        if first.kind is not FrameKind.ITEM:
            raise RuntimeError(f"expected first item, got {first.kind.name}")
        frames = 1
        while True:
            frame = receive_frame(connection)
            if frame.kind is FrameKind.ITEM:
                frames += 1
                continue
            if frame.kind is FrameKind.ERROR:
                raise RuntimeError(frame.payload.decode("utf-8", errors="replace"))
            if frame.kind is FrameKind.TERMINAL:
                if frame.sequence != frames:
                    raise RuntimeError(
                        f"terminal declares {frame.sequence} frames, received {frames}"
                    )
                finished = time.perf_counter_ns()
                break
        ttfb_ms = (first_seen - started) / 1_000_000
        seconds = (finished - first_seen) / 1_000_000_000
        remaining_bytes = max(frames - 1, 0) * size
        mib_per_second = (
            remaining_bytes / (1024 * 1024) / seconds if seconds > 0 else 0.0
        )
        return ttfb_ms, mib_per_second


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=256)
    parser.add_argument("--frame-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    if args.frames < 2 or args.frame_bytes <= 0 or args.runs <= 0:
        parser.error("frames must be >= 2; frame-bytes and runs must be positive")

    with tempfile.TemporaryDirectory(prefix="er-bench-", dir="/tmp") as root:
        server = HostServer(Path(root) / "host.sock")
        server.add(
            HostedFunction(
                name="er.payloads",
                fn=payloads,
                signature=derive(payloads, context_type=Context),
            )
        )
        with server:
            run_once(server.socket_path, 2, min(args.frame_bytes, 4096))
            results = [
                run_once(server.socket_path, args.frames, args.frame_bytes)
                for _ in range(args.runs)
            ]

    ttfb = sorted(result[0] for result in results)
    throughput = sorted(result[1] for result in results)
    print(
        json.dumps(
            {
                "scope": "easyremote_resident_host_unix_socket",
                "protocol": "binary_v1",
                "frames_per_run": args.frames,
                "frame_bytes": args.frame_bytes,
                "runs": args.runs,
                "ttfb_ms": {
                    "median": statistics.median(ttfb),
                    "max": max(ttfb),
                },
                "throughput_mib_s": {
                    "median": statistics.median(throughput),
                    "min": min(throughput),
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
