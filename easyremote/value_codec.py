"""Explicit Python value codecs shared by schema, caller and provider.

Register the same codec on both endpoints before declaring abilities. Wire
values never select or import Python classes; local annotations select decoders.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any

from ._json import dumps_wire


@dataclass(frozen=True)
class ValueCodec:
    """One value type's JSON schema and inverse conversion functions."""

    python_type: type
    schema: dict[str, Any]
    encode: Callable[[Any], Any]
    decode: Callable[[Any], Any]


_codecs: dict[type, ValueCodec] = {}
_lock = RLock()


def register_value_codec(codec: ValueCodec) -> None:
    """Register once at process setup; conflicting registrations fail."""
    if not isinstance(codec.python_type, type):
        raise TypeError("codec python_type must be a class")
    if not isinstance(codec.schema, dict):
        raise TypeError("codec schema must be a JSON schema object")
    if not callable(codec.encode) or not callable(codec.decode):
        raise TypeError("codec encode and decode must be callable")
    dumps_wire(codec.schema, what="value codec schema")
    with _lock:
        if codec.python_type in _codecs:
            raise ValueError(
                f"codec already registered for {codec.python_type.__name__}"
            )
        _codecs[codec.python_type] = ValueCodec(
            codec.python_type, deepcopy(codec.schema), codec.encode, codec.decode
        )


def codec_for(annotation: Any) -> ValueCodec | None:
    if not isinstance(annotation, type):
        return None
    with _lock:
        codec = _codecs.get(annotation)
    if codec is not None:
        return codec
    # Optional NumPy support without importing a missing optional dependency.
    if annotation.__module__ == "numpy" and annotation.__name__ == "ndarray":
        from ._numpy_codec import array_codec

        return array_codec()
    return None
