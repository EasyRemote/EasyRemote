"""`@remote` as a class attribute — the descriptor (property) form.

Start 05_gpu_cluster_node.py first. Its default model bodies are deterministic
fixtures; this run verifies remote contracts, not GPU inference.

A `@remote` stub is a descriptor, so it can live on a class body just
like a method. Declared there it follows the `property` playbook:

- the attribute name becomes the ability name (no second naming), and
- accessing it through an instance binds it to that host — `self` is
  stripped from the wire arguments and the host's own client is reused.

Gather a device's capabilities on one class and let each instance carry
its own client. Module-level `@remote` (see 02_hello_client.py) still
works exactly as before.
"""

from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote


class GPUCluster:
    """A host object that groups the abilities of one device pool."""

    def __init__(self, client: Client) -> None:
        # The descriptor resolves the client from `self.client` (or
        # `self._client`) when the stub itself was declared without one.
        self.client = client

    @remote
    def ai_inference(self, prompt: str, max_tokens: int = 64) -> str:
        # Body never runs; the signature is the asset. `self` is stripped
        # before dispatch, so the wire carries only prompt / max_tokens.
        ...

    @remote
    def embed(self, text: str) -> list[float]: ...

    @remote(name="summarize")  # an explicit name wins over the attribute
    def summarise(self, text: str, max_words: int = 12) -> str: ...


if __name__ == "__main__":
    cluster = GPUCluster(Client(invocation_policy=FreshRoot(ResolvedTargetSubject())))

    prediction = cluster.ai_inference("hello easynet")
    embedding = cluster.embed("vectorise me")
    summary = cluster.summarise("one two three " * 8)
    assert isinstance(prediction, str) and prediction
    assert len(embedding) == 8 and abs(sum(x * x for x in embedding) - 1) < 1e-9
    assert summary == "one two three one two three one two three one two three…"
    print("ai_inference ->", prediction)
    print("embed        ->", embedding)
    print("summarize    ->", summary)

    # Class access yields the descriptor itself (like `property`).
    print("descriptor   ->", type(GPUCluster.ai_inference).__name__)
