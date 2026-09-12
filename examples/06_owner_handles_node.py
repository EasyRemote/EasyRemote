"""Create a native Agent and publish its greeting ability through EasyRemote.

This is an owner-routing example, not an LLM demonstration. The registered
Agent's custom greet ability runs a resident Python function; the default
model-backed chat ability is not replaced or invoked.
"""

import json
import time
from pathlib import Path

from easyremote import Client, ComputeNode, FreshRoot, ResolvedTargetSubject

AGENT_NAME = "owner-handles-demo"
node = ComputeNode()


@node.register
def ai_inference(prompt: str, max_tokens: int = 64) -> str:
    if not prompt or len(prompt) > 4096 or not 1 <= max_tokens <= 512:
        raise ValueError("provide a bounded prompt and max_tokens between 1 and 512")
    return "demo: " + " ".join(prompt.split()[:max_tokens])


@node.register
def greet(prompt: str) -> str:
    if not prompt.strip() or len(prompt) > 4096:
        raise ValueError("prompt must contain 1 to 4096 characters")
    return f"Alice received: {prompt}"


def main() -> None:
    client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))
    created = False
    try:
        node.start()
        if any(agent.name == AGENT_NAME for agent in client.agents.list()):
            raise RuntimeError(
                f"Agent {AGENT_NAME} already exists; use a fresh test Runtime"
            )
        client.agents.add(
            AGENT_NAME, kind="claude-code", root_path=Path.cwd() / "owner-agent"
        )
        created = True
        manifest = f"""schema_version = "2"
name = "greet"
description = "Bounded greeting owned by the example Agent."
admission_action = "invoke"
exposure = "task"
[input_schema]
type = "object"
required = ["prompt"]
additionalProperties = false
[input_schema.properties.prompt]
type = "string"
minLength = 1
maxLength = 4096
[output_schema]
type = "string"
[exec]
kind = "host_stream"
host_socket = {json.dumps(str(node.host_socket))}
function = "er.greet"
protocol = "binary_v1"
"""
        result = client.agents.put_abilities(AGENT_NAME, [manifest])
        if result.get("state") != "committed":
            raise RuntimeError(f"Agent publication did not commit: {result}")
        print("Agent and ability committed; waiting for Hub publication", flush=True)
        deadline = time.monotonic() + 120
        while True:
            row = next(
                (agent for agent in client.agents.list() if agent.name == AGENT_NAME),
                None,
            )
            if row is not None and row.raw.get("publication_state") == "published":
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "Agent committed but not published; check the paired Hub connection"
                )
            time.sleep(1)
        print("Native Agent and greet ability published", flush=True)
        node.serve()
    finally:
        try:
            if created:
                client.agents.stop(AGENT_NAME)
        finally:
            node.stop()
            client.close()


if __name__ == "__main__":
    main()
