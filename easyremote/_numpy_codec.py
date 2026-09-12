"""Bounded, exact numeric ndarray values inside invocation JSON arguments."""

from __future__ import annotations

import base64
import math
from importlib import import_module
from typing import Any

from .value_codec import ValueCodec

MAX_ARRAY_BYTES = 16 * 1024 * 1024
MAX_ARRAY_DIMENSIONS = 32


def array_codec() -> ValueCodec:
    np = import_module("numpy")

    return ValueCodec(
        np.ndarray,
        {
            "type": "object",
            "required": ["dtype", "shape", "data"],
            "additionalProperties": False,
            "properties": {
                "dtype": {"type": "string", "maxLength": 64},
                "shape": {
                    "type": "array",
                    "maxItems": MAX_ARRAY_DIMENSIONS,
                    "items": {"type": "integer", "minimum": 0},
                },
                "data": {
                    "type": "string",
                    "contentEncoding": "base64",
                    "maxLength": ((MAX_ARRAY_BYTES + 2) // 3) * 4,
                },
            },
        },
        _encode,
        _decode,
    )


def _checked_dtype(value: Any) -> Any:
    np = import_module("numpy")

    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("invalid ndarray dtype")
    dtype = np.dtype(value)
    if dtype.hasobject or dtype.fields is not None or dtype.kind not in "biufcmM":
        raise ValueError("ndarray codec requires a numeric or datetime dtype")
    return dtype


def _encode(value: Any) -> dict[str, Any]:
    _checked_dtype(value.dtype.str)
    if value.ndim > MAX_ARRAY_DIMENSIONS or value.nbytes > MAX_ARRAY_BYTES:
        raise ValueError("ndarray exceeds value codec limits; use chunked transfer")
    return {
        "dtype": value.dtype.str,
        "shape": list(value.shape),
        "data": base64.b64encode(value.tobytes(order="C")).decode("ascii"),
    }


def _decode(value: Any) -> Any:
    np = import_module("numpy")

    if not isinstance(value, dict) or set(value) != {"dtype", "shape", "data"}:
        raise ValueError("invalid ndarray envelope")
    dtype = _checked_dtype(value["dtype"])
    shape = value["shape"]
    if (
        not isinstance(shape, list)
        or len(shape) > MAX_ARRAY_DIMENSIONS
        or any(type(n) is not int or n < 0 or n > MAX_ARRAY_BYTES for n in shape)
    ):
        raise ValueError("invalid ndarray shape")
    size = math.prod(shape) * dtype.itemsize
    data = value["data"]
    if (
        size > MAX_ARRAY_BYTES
        or not isinstance(data, str)
        or len(data) != ((size + 2) // 3) * 4
    ):
        raise ValueError("ndarray byte length exceeds limit or mismatches shape")
    raw = base64.b64decode(data, validate=True)
    if len(raw) != size:
        raise ValueError("ndarray byte length mismatches shape")
    return np.frombuffer(raw, dtype=dtype).reshape(tuple(shape)).copy()
