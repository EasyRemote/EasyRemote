#!/usr/bin/env python3
"""Measure inter-frame arrival gaps to prove streaming is real.

If streaming is genuine, the gap between consecutive frame *receive*
times tracks the server's GAP (0.4s) and the first frame arrives almost
immediately. If the stream were batched, the first frame would be late
and the rest would land together. Run ``04_streaming_node.py`` first.
"""

import time

from easyremote import Client

client = Client(timeout=30)
GAP = 0.4
N = 5


def probe(label: str, fn: str, **kwargs) -> None:
    t0 = time.perf_counter()
    recv_ms = []
    for _frame in client.stream(fn, **kwargs):
        recv_ms.append((time.perf_counter() - t0) * 1000)

    gaps = [recv_ms[i] - recv_ms[i - 1] for i in range(1, len(recv_ms))]
    print(f"\n=== {label}: {len(recv_ms)} frames ===")
    for off in recv_ms:
        print(f"   recv @ {off:7.1f} ms")
    if gaps:
        mean = sum(gaps) / len(gaps)
        print(f"   inter-frame gaps (ms): {[round(g, 1) for g in gaps]}")
        print(f"   mean gap {mean:.0f} ms  (server GAP = {GAP * 1000:.0f} ms)")
        incremental = all(g > GAP * 1000 * 0.5 for g in gaps)
        print(
            "   VERDICT:",
            "✅ REAL STREAMING (incremental)"
            if incremental
            else "❌ BATCHED (arrived together)",
        )


if __name__ == "__main__":
    probe("sync generator (ticker)", "ticker", n=N)
    probe("async generator (aticker)", "aticker", n=N)

    t0 = time.perf_counter()
    result = client.execute("slow_add", a=2, b=3)
    ms = (time.perf_counter() - t0) * 1000
    print("\n=== async unary (slow_add) ===")
    print(f"   slow_add(2, 3) = {result}  in {ms:.0f} ms"
          f"  (expect ≳ {GAP * 1000:.0f} ms = the awaited sleep)")
