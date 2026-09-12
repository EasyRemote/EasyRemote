#!/usr/bin/env python3
"""Client caller for the decorator quickstart.

Recreates the v1 ``examples/decorator_route/client.py`` demo on the v2
API: transparent ``@remote`` stubs, async fan-out, multimodal bytes,
and a warm-path latency report.
"""

import asyncio
import base64
import os
import statistics
import time

from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

GATEWAY_ADDRESS = os.getenv("EASYREMOTE_GATEWAY_ADDRESS")  # optional, classic shape

client = Client(
    GATEWAY_ADDRESS,
    invocation_policy=FreshRoot(ResolvedTargetSubject()),
)


@remote(client=client)
def add_numbers(a: int, b: int) -> int:
    # The signature describes the remote call; this body never executes.
    pass


@remote(client=client)
def multiply_numbers(a: int, b: int) -> int:
    pass


@remote(client=client)
def summarize(text: str, max_words: int = 12) -> str:
    pass


@remote(client=client)
def make_thumbnail(image: bytes, size: int = 64) -> bytes: ...


class DecoratorDemo:
    """Direct calls, async fan-out, multimodal, then a latency report."""

    def run(self) -> None:
        print(f"add_numbers(12, 30)      -> {add_numbers(12, 30)}")
        print(f"multiply_numbers(7, 8)   -> {multiply_numbers(7, 8)}")
        print(f"summarize(...)           -> {summarize('one two three ' * 8)}")

        thumb = make_thumbnail(image=b"\x89PNG" + bytes(512), size=16)
        decoded = base64.b64decode(thumb) if isinstance(thumb, str) else thumb
        assert decoded == (b"\x89PNG" + bytes(512))[:16]
        print(f"make_thumbnail(512B)     -> {len(decoded)} bytes")

        asyncio.run(self.fan_out())
        self.latency_report()

    async def fan_out(self) -> None:
        """Concurrent calls through the async mirror — no extra API."""
        started = time.perf_counter()
        results = await asyncio.gather(
            *(client.aio.execute("add_numbers", a=i, b=i) for i in range(8))
        )
        assert results == [2 * i for i in range(8)]
        elapsed = (time.perf_counter() - started) * 1000
        print(f"async fan-out x8         -> {results}  ({elapsed:.0f}ms total)")

    def latency_report(self, rounds: int = 20) -> None:
        samples = []
        for _ in range(rounds):
            started = time.perf_counter()
            add_numbers(1, 1)
            samples.append((time.perf_counter() - started) * 1000)
        print(
            f"warm latency x{rounds}        -> p50 {statistics.median(samples):.1f}ms"
            f" / p95 {sorted(samples)[int(rounds * 0.95) - 1]:.1f}ms"
        )


if __name__ == "__main__":
    DecoratorDemo().run()
