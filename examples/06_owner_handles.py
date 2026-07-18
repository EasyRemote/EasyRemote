"""Owner handles — the client-side mirror of ``@node.register``.

The serving side groups local functions on a ``ComputeNode`` and publishes
them with ``@node.register``. The calling side is symmetric: a handle to an
ability owner (``client.device`` / ``client.agent`` / ``client.hub``) carries
the target identity, and ``@handle.remote`` declares a typed stub bound to
that owner. The owner lives on the handle, never in the call site.

    # serving side                      # calling side (symmetric)
    node = ComputeNode()                gpu   = client.device("gpu-2")
    @node.register                      @gpu.remote
    def chat(...): ...                  def chat(...): ...

daemon support (verified against EasyNet-Cli): device, agent, and hub
callees are first-class routes. A full cross-realm owner URA is accepted and
encoded, but only routes where the daemon's federation peers are configured.
"""

from easyremote import Client, FreshRoot, ResolvedTargetSubject

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))

# A handle per owner. The id / token is all the call site needs.
gpu = client.device("gpu-2")  # a device in this realm
alice = client.agent("u-alice.chatbot")  # an agent: <user-id>.<agent-id>
hub = client.hub()  # the realm hub


@gpu.remote
def ai_inference(prompt: str, max_tokens: int = 64) -> str:
    # Bound to gpu-2; the body never runs (the signature is the asset).
    ...


@alice.remote
def chat(prompt: str) -> str: ...


if __name__ == "__main__":
    print("gpu.ai_inference ->", ai_inference("hello from gpu-2"))
    print("alice.chat       ->", chat("hi alice"))

    # Ad-hoc dispatch without declaring a stub — same handle, .call / .stream.
    print("hub.route        ->", hub.call("route", target="gpu-2"))
    print("alice (ad-hoc)   ->", alice.call("chat", prompt="hi again"))
