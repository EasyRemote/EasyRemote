"""Strict JSON helpers for EasyRemote wire boundaries.

Python's ``json.dumps`` accepts ``NaN`` and infinities by default, while
the daemon side uses standards-compliant JSON. This module is the single
place that turns Python values into wire JSON so every transport path
rejects non-finite numbers with the same taxonomy.
"""

from __future__ import annotations

import json
from typing import Any

from .errors import InvalidArgument

__all__ = ["dumps_wire"]


def dumps_wire(
    value: Any,
    *,
    what: str,
    sort_keys: bool = False,
    indent: int | None = None,
) -> str:
    """Encode a value as compact UTF-8 JSON text for daemon/host wires.

    Args:
        value: JSON-compatible Python value.
        what: Human-readable boundary name for the error message.
        sort_keys: Whether to sort object keys for deterministic hashing.
        indent: Pretty-print indentation for files such as ability manifests.
            When omitted, output stays compact for wire boundaries and hashes.

    Raises:
        InvalidArgument: if ``value`` contains a non-finite float or is
            otherwise not JSON-serializable.
    """
    try:
        kwargs: dict[str, Any] = {
            "ensure_ascii": False,
            "allow_nan": False,
            "sort_keys": sort_keys,
        }
        if indent is None:
            kwargs["separators"] = (",", ":")
        else:
            kwargs["indent"] = indent
        return json.dumps(value, **kwargs)
    except (TypeError, ValueError) as exc:
        raise InvalidArgument(
            f"{what} must be standards-compliant JSON: {type(exc).__name__}: {exc}",
            reason="invalid_json_payload",
        ) from None
