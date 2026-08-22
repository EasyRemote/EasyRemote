"""Publish one model that remains warm inside the provider process."""

import hashlib
import math

from easyremote import ComputeNode

node = ComputeNode(namespace="er")


class WarmEmbeddingModel:
    """Small runnable adapter; replace only this class with the real model."""

    dimensions = 8

    def embed(self, text: str) -> list[float]:
        digest = hashlib.blake2b(
            text.encode("utf-8"), digest_size=self.dimensions
        ).digest()
        values = [byte / 255.0 for byte in digest]
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [round(value / norm, 6) for value in values]


MODEL = WarmEmbeddingModel()


@node.register(description="Generate an embedding with a provider-resident model.")
def embed_text(text: str) -> list[float]:
    if not text.strip():
        raise ValueError("text must not be empty")
    if len(text) > 4_096:
        raise ValueError("text must contain at most 4,096 characters")
    return MODEL.embed(text)


if __name__ == "__main__":
    node.serve()
