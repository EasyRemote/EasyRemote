"""Publish finite, read-only incident evidence instead of shell access."""

import time
from collections.abc import Iterator

from easyremote import ComputeNode, Context

node = ComputeNode(namespace="er")

SERVICE_STATE = {
    "api": {"p95_ms": 840, "error_rate": 0.037, "recent_release": "api-1842"},
    "indexer": {
        "p95_ms": 210,
        "error_rate": 0.004,
        "recent_release": "indexer-611",
    },
    "worker": {
        "p95_ms": 390,
        "error_rate": 0.012,
        "recent_release": "worker-902",
    },
}


def require_service(service: str) -> dict[str, str | int | float]:
    try:
        return SERVICE_STATE[service]
    except KeyError as exc:
        raise ValueError(f"service must be one of {sorted(SERVICE_STATE)}") from exc


@node.register(description="Return one bounded, caller-attributed diagnosis.")
def diagnose_service(
    ctx: Context,
    service: str,
    window_minutes: int = 15,
) -> dict[str, str | int | float]:
    state = require_service(service)
    if not 1 <= window_minutes <= 60:
        raise ValueError("window_minutes must be between 1 and 60")
    return {
        "service": service,
        "window_minutes": window_minutes,
        "status": "degraded" if float(state["p95_ms"]) > 500 else "healthy",
        "p95_ms": state["p95_ms"],
        "error_rate": state["error_rate"],
        "recent_release": state["recent_release"],
        "requested_by": ctx.caller,
        "invocation_id": ctx.invocation_id,
    }


@node.register(description="Stream a finite sequence of normalized evidence.")
def stream_evidence(
    service: str, samples: int = 5
) -> Iterator[dict[str, str | int | float]]:
    state = require_service(service)
    if not 1 <= samples <= 10:
        raise ValueError("samples must be between 1 and 10")
    for sequence in range(1, samples + 1):
        yield {"sequence": sequence, "service": service, **state}
        time.sleep(0.1)


if __name__ == "__main__":
    node.serve()
