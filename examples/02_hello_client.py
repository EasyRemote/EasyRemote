"""Call a capability three ways, shallow to deep."""

from easyremote import Client, remote

client = Client()

# L0 — result-first, like calling a local function
print(client.execute("ai_inference", prompt="hello easynet"))


# L1 — a typed stub: positional args and defaults bound locally
@remote
def ai_inference(prompt: str, max_tokens: int = 64) -> dict: ...


print(ai_inference("hello again"))

# L2 — the full invocation object: seven-tuple in, receipts out
invocation = client.invoke("ai_inference", prompt="inspect me")
print("state:", invocation.state.name)
print("tuple.subject:", invocation.tuple.subject)
print("result:", invocation.result())
