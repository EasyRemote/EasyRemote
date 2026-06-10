"""Publish a local function as a capability and keep it warm.

After this prints "serving", the function is callable (Client),
discoverable (MCP via `easynet mcp_server`), and composable
(Pipeline / EAL) — one registration, three consumption surfaces.
"""

from easyremote import ComputeNode

node = ComputeNode()  # namespace "er"; agent root comes from the daemon


@node.register
def ai_inference(prompt: str, max_tokens: int = 64) -> dict:
    """Pretend-inference: swap in your real model here."""
    return {"completion": f"echo({prompt})", "max_tokens": max_tokens}


if __name__ == "__main__":
    print(f"serving {[a.qualified_name for a in node.abilities]} — Ctrl-C to stop")
    node.serve()
