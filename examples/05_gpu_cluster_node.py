"""Companion provider for 05_remote_on_class.py.

Deterministic inference/embedding/summarization fixtures exercise the remote
contracts without downloading models. They do not perform GPU computation.
Replace these bodies with your model calls to exercise a real GPU deployment.
"""

import hashlib
import math

from easyremote import ComputeNode

node = ComputeNode()


def validate_text(text: str) -> None:
    if not text.strip() or len(text) > 16_384:
        raise ValueError("text must contain 1 to 16384 characters")


@node.register
def ai_inference(prompt: str, max_tokens: int = 64) -> str:
    validate_text(prompt)
    if not 1 <= max_tokens <= 512:
        raise ValueError("max_tokens must be between 1 and 512")
    return "demo: " + " ".join(prompt.split()[:max_tokens])


@node.register
def embed(text: str) -> list[float]:
    validate_text(text)
    values = [value - 127.5 for value in hashlib.sha256(text.encode()).digest()[:8]]
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


@node.register
async def summarize(text: str, max_words: int = 12) -> str:
    validate_text(text)
    if not 1 <= max_words <= 512:
        raise ValueError("max_words must be between 1 and 512")
    words = text.split()
    return " ".join(words[:max_words]) + ("…" if len(words) > max_words else "")


if __name__ == "__main__":
    node.serve()
