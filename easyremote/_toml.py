"""Minimal TOML writer for daemon configuration files.

The stdlib only reads TOML. EasyRemote writes one constrained document:
nested tables with string/int/float/bool scalars and arrays. Keeping the
writer here avoids ad hoc string interpolation in product config paths.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from .errors import InvalidArgument

__all__ = ["dumps"]

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def dumps(document: dict[str, Any]) -> str:
    """Serialize a constrained TOML document."""
    lines: list[str] = []
    _emit_table(document, prefix=(), lines=lines)
    return "\n".join(lines) + "\n"


def _emit_table(
    table: dict[str, Any], *, prefix: tuple[str, ...], lines: list[str]
) -> None:
    scalars = {
        key: value for key, value in table.items() if not isinstance(value, dict)
    }
    subtables = {key: value for key, value in table.items() if isinstance(value, dict)}
    for key, value in scalars.items():
        lines.append(f"{_key(key)} = {_value(value)}")
    for key, value in subtables.items():
        path = (*prefix, key)
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"[{'.'.join(_key(part) for part in path)}]")
        _emit_table(value, prefix=path, lines=lines)


def _key(key: str) -> str:
    return key if _BARE_KEY.match(key) else json.dumps(key, ensure_ascii=False)


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidArgument(
                f"TOML number must be finite, got {value!r}",
                reason="invalid_toml_value",
            )
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    raise InvalidArgument(
        f"unsupported TOML value type: {type(value).__name__}",
        reason="invalid_toml_value",
    )
