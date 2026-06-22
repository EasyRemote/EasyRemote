#!/usr/bin/env python3
"""Compute node for the decorator quickstart.

Recreates the v1 ``examples/decorator_route/compute_node.py`` demo on
the v2 (EasyNet-native) API — same shape, richer payloads: sync math,
an async summarizer, and a multimodal (bytes-in/bytes-out) thumbnail
function. Functions stay warm in this process; the daemon reaches them
through its host_stream executor and the warm host socket.
"""

from easyremote import ComputeNode


class MathComputeNode:
    """Registers business functions and serves them as device abilities."""

    def __init__(self, gateway: str | None = None) -> None:
        self._node = ComputeNode(gateway)
        self._register_functions()

    def _register_functions(self) -> None:
        @self._node.register(name="add_numbers", description="Add two integers.")
        def add_numbers(a: int, b: int) -> int:
            return a + b

        @self._node.register(
            name="multiply_numbers", description="Multiply two integers."
        )
        def multiply_numbers(a: int, b: int) -> int:
            return a * b

        # Async functions register identically — the warm host awaits them.
        @self._node.register(description="Summarize text (async).")
        async def summarize(text: str, max_words: int = 12) -> str:
            words = text.split()
            return " ".join(words[:max_words]) + ("…" if len(words) > max_words else "")

        # Multimodal: bytes travel as base64 (schema contentEncoding),
        # both directions — send an image, get a "thumbnail" back.
        @self._node.register(description="Center-crop bytes as a fake thumbnail.")
        def make_thumbnail(image: bytes, size: int = 64) -> bytes:
            return image[:size]

    def serve(self) -> None:
        self._node.serve()


if __name__ == "__main__":
    MathComputeNode().serve()
