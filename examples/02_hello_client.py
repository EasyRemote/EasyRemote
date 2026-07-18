"""Call a capability through the result-first and typed-stub surfaces."""

from easyremote import Client, remote

client = Client()

# L0 — result-first, like calling a local function
print(client.execute("ai_inference", prompt="hello easynet"))


# L1 — a typed stub: positional args and defaults bound locally
@remote
def ai_inference(prompt: str, max_tokens: int = 64) -> dict: ...


print(ai_inference("hello again"))

# L2 — inspect the seven-tuple before dispatch. EasyRemote-hosted
# abilities register as host_stream, so dispatch them with call()/stream()
# after inspection rather than PreparedInvocation.send() / invoke().
prepared = client.prepare("ai_inference", prompt="inspect me")
print("tuple.subject:", prepared.tuple.subject_ura)
print("result:", client.call("ai_inference", prompt="inspect me"))
