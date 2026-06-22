#!/usr/bin/env python3
"""Server side: register functions as device abilities with @node.register.

One decorator, every Python function shape — the node auto-detects each
(unary / *args / **kwargs / async / generator / Context-taking) and
serves it warm. Run this, then run `remote_demo_client.py` in another
terminal.
"""

from easyremote import ComputeNode, Context

node = ComputeNode()  # namespace "er"; identity from the local daemon


@node.register
def add(a: int, b: int) -> int:
    """Plain unary."""
    return a + b


@node.register
def total(*nums: int) -> int:
    """Variadic positionals (*args)."""
    return sum(nums)


@node.register
def merge(base: int, **extra: int) -> dict:
    """Keyword variadics (**kwargs)."""
    return {"base": base, **extra}


@node.register
async def summarize(text: str, max_words: int = 12) -> str:
    """Async function — the warm host awaits it."""
    words = text.split()
    return " ".join(words[:max_words]) + ("…" if len(words) > max_words else "")


@node.register
def countdown(n: int):
    """Generator — streams one frame per yield, live."""
    for i in range(n, 0, -1):
        yield f"T-{i}"


@node.register
def whoami(ctx: Context, note: str) -> dict:
    """Context-taking — reads who is calling (caller URA + invocation id)."""
    return {"note": note, "caller": ctx.caller, "invocation_id": ctx.invocation_id}


if __name__ == "__main__":
    served = sorted(a.qualified_name for a in node.abilities)
    print(f"serving {served} — Ctrl-C to stop", flush=True)
    node.serve()
