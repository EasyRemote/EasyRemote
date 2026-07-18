#!/usr/bin/env python3
"""Client side: call the remote abilities with @remote typed stubs.

`@remote` turns a signature into a transparent call into the daemon —
the body never runs; the stub maps your args and dispatches. Generators
are consumed live with `.stream(...)`; everything else returns its value
directly. Run `remote_demo_node.py` first.
"""

from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))


@remote(client=client)
def add(a: int, b: int) -> int: ...


@remote(client=client)
def total(*nums: int) -> int: ...


@remote(client=client)
def merge(base: int, **extra: int) -> dict: ...


@remote(client=client)
def summarize(text: str, max_words: int = 12) -> str: ...


@remote(client=client)
def countdown(n: int): ...


@remote(client=client)
def whoami(note: str) -> dict: ...


if __name__ == "__main__":
    print("add(2, 3)                 ->", add(2, 3))
    print("total(1, 2, 3, 4)         ->", total(1, 2, 3, 4))
    print("merge(base=10, x=1, y=2)  ->", merge(base=10, x=1, y=2))
    print(
        "summarize(...)            ->",
        summarize("one two three four five six", max_words=3),
    )

    print("countdown(3) live stream  ->", end=" ", flush=True)
    for frame in countdown.stream(3):
        print(frame, end=" ", flush=True)
    print()

    print("whoami('hi')              ->", whoami("hi"))
