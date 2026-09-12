"""Bounded, exact PyTorch tensor values inside invocation JSON arguments.

Tensors are carried as raw little-endian element bytes rather than through
NumPy. That keeps dtypes NumPy cannot represent — ``bfloat16`` above all —
exact instead of silently widening or failing at the bridge.
"""

from __future__ import annotations

import base64
import math
from importlib import import_module
from typing import Any

from .value_codec import ValueCodec

MAX_TENSOR_BYTES = 16 * 1024 * 1024
MAX_TENSOR_DIMENSIONS = 32

# Element size per dtype, so decode can check the declared shape against the
# payload length before allocating anything.
_ITEMSIZE = {
    "torch.bool": 1,
    "torch.uint8": 1,
    "torch.int8": 1,
    "torch.int16": 2,
    "torch.float16": 2,
    "torch.bfloat16": 2,
    "torch.int32": 4,
    "torch.float32": 4,
    "torch.int64": 8,
    "torch.float64": 8,
    "torch.complex64": 8,
    "torch.complex128": 16,
}


def tensor_codec() -> ValueCodec:
    torch = import_module("torch")

    return ValueCodec(
        torch.Tensor,
        {
            "type": "object",
            "required": ["dtype", "shape", "data"],
            "additionalProperties": False,
            "properties": {
                "dtype": {"type": "string", "enum": sorted(_ITEMSIZE)},
                "shape": {
                    "type": "array",
                    "maxItems": MAX_TENSOR_DIMENSIONS,
                    "items": {"type": "integer", "minimum": 0},
                },
                "data": {
                    "type": "string",
                    "maxLength": ((MAX_TENSOR_BYTES + 2) // 3) * 4,
                },
            },
        },
        _encode,
        _decode,
    )


def _checked_dtype(value: Any) -> int:
    if not isinstance(value, str) or value not in _ITEMSIZE:
        raise ValueError(f"unsupported tensor dtype {value!r}")
    return _ITEMSIZE[value]


def _encode(value: Any) -> dict[str, Any]:
    torch = import_module("torch")

    if value.requires_grad:
        # The autograd graph does not cross the wire. Detaching silently would
        # hand back a tensor the caller still believes is differentiable.
        raise ValueError(
            "tensor requires grad; call .detach() before sending it"
        )
    if value.device.type != "cpu":
        raise ValueError(
            f"tensor is on device {value.device}; call .cpu() before sending it"
        )
    if value.is_sparse:
        raise ValueError("sparse tensors are not supported by the value codec")
    _checked_dtype(str(value.dtype))
    if value.dim() > MAX_TENSOR_DIMENSIONS:
        raise ValueError("tensor exceeds value codec limits; use chunked transfer")

    # A sliced or transposed tensor's storage is not in row-major order, so its
    # raw bytes would decode to a different tensor. `reshape(-1)` also gives a
    # 1-D view that can be byte-viewed; a 0-dim tensor cannot be viewed
    # directly, while `shape` below still records 0 dims so decode restores it.
    flat = value.detach().contiguous().reshape(-1)
    if flat.numel() * flat.element_size() > MAX_TENSOR_BYTES:
        raise ValueError("tensor exceeds value codec limits; use chunked transfer")
    raw = flat.view(torch.uint8).numpy().tobytes() if flat.numel() else b""
    return {
        "dtype": str(value.dtype),
        "shape": list(value.shape),
        "data": base64.b64encode(raw).decode("ascii"),
    }


def _decode(value: Any) -> Any:
    torch = import_module("torch")

    if not isinstance(value, dict) or set(value) != {"dtype", "shape", "data"}:
        raise ValueError("invalid tensor envelope")
    itemsize = _checked_dtype(value["dtype"])
    dtype = getattr(torch, value["dtype"].removeprefix("torch."))
    shape = value["shape"]
    if (
        not isinstance(shape, list)
        or len(shape) > MAX_TENSOR_DIMENSIONS
        or any(type(n) is not int or n < 0 or n > MAX_TENSOR_BYTES for n in shape)
    ):
        raise ValueError("invalid tensor shape")
    size = math.prod(shape) * itemsize
    data = value["data"]
    if (
        size > MAX_TENSOR_BYTES
        or not isinstance(data, str)
        or len(data) != ((size + 2) // 3) * 4
    ):
        raise ValueError("tensor byte length exceeds limit or mismatches shape")
    if not size:
        return torch.empty(tuple(shape), dtype=dtype)
    raw = base64.b64decode(data, validate=True)
    if len(raw) != size:
        raise ValueError("tensor byte length mismatches shape")
    # `frombuffer` over a mutable copy: the decoded tensor must own its memory
    # rather than alias a buffer the caller could later mutate.
    return (
        torch.frombuffer(bytearray(raw), dtype=torch.uint8)
        .view(dtype)
        .reshape(tuple(shape))
    )
