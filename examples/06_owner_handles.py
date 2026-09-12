"""Device, Agent and Hub handles. Start 06_owner_handles_node.py first.

The provider creates a native Agent and custom greeting ability. The Python
chat stub binds to greet because the built-in chat name is reserved for the
Runtime's structured model interface. No model driver is executed in this case.
"""

import argparse

from easynet_sdk import owner_ability_ura

from easyremote import Client, ExplicitSubject, FreshRoot, ResolvedTargetSubject
from easyremote.identity import LocalIdentity, device_ura


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", help="Device ID; defaults to current Runtime")
    parser.add_argument("--agent", default="owner-handles-demo")
    args = parser.parse_args()
    identity = LocalIdentity.load()
    client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))
    device_id = args.device or identity.node_id
    gpu = client.device(device_id)
    alice = client.agent(args.agent)
    hub = client.hub()

    @gpu.remote
    def ai_inference(prompt: str, max_tokens: int = 64) -> str: ...

    greeting = owner_ability_ura(alice.owner_ura, "greet")

    @alice.remote(name=greeting)
    def chat(prompt: str) -> str: ...

    # Query routing for this Device; it is the subject of the Hub read.
    @hub.remote(
        name="federation.resolve",
        invocation_policy=FreshRoot(ExplicitSubject(gpu.device_ura)),
    )
    def route() -> dict: ...

    prediction = ai_inference("hello from gpu-2")
    reply = chat("hi alice")
    again = alice.call(greeting, prompt="hi again")
    assert prediction == "demo: hello from gpu-2"
    assert reply == "Alice received: hi alice"
    assert again == "Alice received: hi again"
    print("gpu.ai_inference ->", prediction)
    print("alice.chat ->", reply)
    print("alice (ad-hoc) ->", again)
    directory = route()
    target = device_ura(identity.realm, device_id)
    routes = [row for row in directory["agents"] if row["ura"] == target]
    assert len(routes) == 1 and routes[0]["status"] == "active", routes
    print("hub.route ->", routes[0])


if __name__ == "__main__":
    main()
