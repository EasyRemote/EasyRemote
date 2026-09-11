"""Bounded Pillow image values inside invocation JSON arguments.

Images are carried in their own encoded container (PNG for exact pixels, or
the source format when it is already compressed) rather than as raw pixel
buffers, because an image's size on the wire is the reason it is an image and
not an array.
"""

from __future__ import annotations

import base64
import io
from importlib import import_module
from typing import Any

from .value_codec import ValueCodec

MAX_IMAGE_BYTES = 16 * 1024 * 1024

# Formats carried through unchanged because re-encoding them would either lose
# quality (JPEG) or waste time for no size win.
_PASSTHROUGH = {"JPEG", "PNG", "WEBP", "GIF", "TIFF", "BMP"}


def image_codec() -> ValueCodec:
    module = import_module("PIL.Image")

    return ValueCodec(
        module.Image,
        {
            "type": "object",
            "required": ["format", "data"],
            "additionalProperties": False,
            "properties": {
                "format": {"type": "string", "maxLength": 16},
                "data": {
                    "type": "string",
                    "maxLength": ((MAX_IMAGE_BYTES + 2) // 3) * 4,
                },
            },
        },
        _encode,
        _decode,
    )


def _encode(value: Any) -> dict[str, Any]:
    # An image loaded from disk keeps its source format; one built in memory
    # has none, and PNG is the lossless default so pixels survive exactly.
    fmt = value.format if value.format in _PASSTHROUGH else "PNG"
    if fmt == "PNG" and value.mode in {"CMYK", "YCbCr"}:
        # PNG cannot represent these modes; TIFF can, and is still lossless.
        fmt = "TIFF"
    buffer = io.BytesIO()
    value.save(buffer, format=fmt)
    raw = buffer.getvalue()
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("image exceeds value codec limits; use chunked transfer")
    return {"format": fmt, "data": base64.b64encode(raw).decode("ascii")}


def _decode(value: Any) -> Any:
    module = import_module("PIL.Image")

    if not isinstance(value, dict) or set(value) != {"format", "data"}:
        raise ValueError("invalid image envelope")
    fmt = value["format"]
    if not isinstance(fmt, str) or fmt not in _PASSTHROUGH:
        raise ValueError(f"unsupported image format {fmt!r}")
    data = value["data"]
    if not isinstance(data, str) or len(data) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
        raise ValueError("image payload exceeds limit")
    raw = base64.b64decode(data, validate=True)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("image payload exceeds limit")
    image = module.open(io.BytesIO(raw))
    # `open` is lazy; force the decode now so a malformed payload fails here
    # rather than at some later attribute access in the caller's code.
    image.load()
    return image
