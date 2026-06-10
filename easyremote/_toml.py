"""Minimal TOML serializer for ability manifests.

The stdlib ships ``tomllib`` (read-only); rather than pull a
dependency for one constrained document shape, this emits exactly the
subset ability manifests need: string/int/float/bool scalars, arrays,
and nested tables. Keys that aren't bare-key-safe (e.g.
``x-easyremote-parameter-order``) are quoted. Round-trip safety is
pinned by tests against ``tomllib``.
"""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = ["dumps"]

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def dumps(document: dict[str, Any]) -> str:
    """Serialize ``document`` to TOML text.

    Scalars and arrays first, then sub-tables — the order TOML
    requires (a scalar after a ``[table]`` header would belong to the
    sub-table).
    """
    lines: list[str] = []
    _emit_table(document, prefix=(), lines=lines)
    return "\n".join(lines) + "\n"


def _emit_table(
    table: dict[str, Any], *, prefix: tuple[str, ...], lines: list[str]
) -> None:
    scalars = {k: v for k, v in table.items() if not isinstance(v, dict)}
    subtables = {k: v for k, v in table.items() if isinstance(v, dict)}

    for key, value in scalars.items():
        lines.append(f"{_key(key)} = {_value(value)}")
    for key, value in subtables.items():
        path = (*prefix, key)
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"[{'.'.join(_key(part) for part in path)}]")
        _emit_table(value, prefix=path, lines=lines)


def _key(key: str) -> str:
    if _BARE_KEY.match(key):
        return key
    return json.dumps(key)  # TOML basic strings share JSON's escapes


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not (
            value == value and abs(value) != float("inf")
        ):
            raise ValueError(f"non-finite float {value!r} is not representable in TOML")
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_inline_value(item) for item in value) + "]"
    raise ValueError(f"unsupported TOML value type: {type(value).__name__}")


def _inline_value(value: Any) -> str:
    if isinstance(value, dict):
        pairs = ", ".join(f"{_key(k)} = {_inline_value(v)}" for k, v in value.items())
        return "{" + pairs + "}"
    return _value(value)
