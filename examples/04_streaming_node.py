#!/usr/bin/env python3
"""Streaming + async, proven incremental (not batched).

Each generator sleeps GAP seconds BETWEEN yields and stamps the wall
clock on every frame, so the client (``04_streaming_client.py``) can
measure inter-frame arrival gaps and prove frames arrive one at a time
— a real per-token pipe, not a collect-then-return.
"""

import asyncio
import time

from easyremote import ComputeNode

node = ComputeNode()  # namespace "er"; identity from the local daemon

GAP = 0.4  # seconds the server waits between frames


@node.register
def ticker(n: int):
    """Sync generator — yield a frame, then sleep GAP before the next."""
    for i in range(n):
        yield {"i": i, "server_emit": time.time()}
        time.sleep(GAP)


@node.register
async def aticker(n: int):
    """Async generator — real ``await`` between frames."""
    for i in range(n):
        yield {"i": i, "server_emit": time.time()}
        await asyncio.sleep(GAP)


@node.register
async def slow_add(a: int, b: int) -> int:
    """Async unary that genuinely awaits — proves the async path is awaited."""
    await asyncio.sleep(GAP)
    return a + b


if __name__ == "__main__":
    served = sorted(a.qualified_name for a in node.abilities)
    print(f"serving {served}  GAP={GAP}s — Ctrl-C to stop", flush=True)
    node.serve()
