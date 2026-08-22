"""Collect structured incident diagnosis and incremental evidence."""

from collections.abc import Iterator
from pprint import pprint

from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))


@remote(client=client)
def diagnose_service(
    service: str,
    window_minutes: int = 15,
) -> dict[str, str | int | float]: ...


@remote(client=client)
def stream_evidence(
    service: str,
    samples: int = 5,
) -> Iterator[dict[str, str | int | float]]: ...


if __name__ == "__main__":
    pprint(diagnose_service("api", window_minutes=15))
    for evidence in stream_evidence.stream("api", samples=3):
        pprint(evidence)
