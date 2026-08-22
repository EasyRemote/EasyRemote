"""Call a model hosted by one explicitly selected GPU device."""

import os

from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))


@remote(client=client, node=os.getenv("EASYREMOTE_GPU_NODE"))
def embed_text(text: str) -> list[float]: ...


if __name__ == "__main__":
    print(embed_text("Capability sharing keeps model custody local."))
