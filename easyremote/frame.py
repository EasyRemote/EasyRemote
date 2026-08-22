"""Typed server-stream payloads for text, audio, image, video and binary data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .errors import InvalidArgument


@dataclass(frozen=True, slots=True)
class StreamFrame:
    """One raw stream payload and its exact IANA media type.

    Yield this from a registered generator to preserve bytes without JSON or
    base64 conversion. Plain Python values continue to travel as
    ``application/json``; bare ``bytes`` use ``application/octet-stream``.
    """

    payload: bytes
    content_type: str

    def __post_init__(self) -> None:
        if not isinstance(self.payload, bytes):
            raise InvalidArgument(
                "StreamFrame payload must be bytes",
                reason="invalid_stream_frame",
            )
        if (
            not isinstance(self.content_type, str)
            or not self.content_type.strip()
            or self.content_type != self.content_type.strip()
            or "/" not in self.content_type
        ):
            raise InvalidArgument(
                "StreamFrame content_type must be a non-empty media type",
                reason="invalid_stream_frame",
            )

    @classmethod
    def text(
        cls,
        value: str,
        *,
        content_type: str = "text/plain; charset=utf-8",
    ) -> StreamFrame:
        return cls(value.encode("utf-8"), content_type)

    @classmethod
    def json(cls, value: Any) -> StreamFrame:
        return cls(
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8"),
            "application/json",
        )
