"""Bounded pandas values inside invocation JSON arguments.

Carried as Arrow IPC bytes rather than CSV or JSON records: Arrow is the only
common format that preserves dtypes, the index, timezone-aware timestamps and
categoricals exactly, which is the whole point of a value codec.
"""

from __future__ import annotations

import base64
import io
from importlib import import_module
from typing import Any

from .value_codec import ValueCodec

MAX_FRAME_BYTES = 16 * 1024 * 1024

_SCHEMA = {
    "type": "object",
    "required": ["kind", "data"],
    "additionalProperties": False,
    "properties": {
        "kind": {"type": "string", "enum": ["frame", "series"]},
        "name": {"type": ["string", "null"]},
        "data": {
            "type": "string",
            "maxLength": ((MAX_FRAME_BYTES + 2) // 3) * 4,
        },
    },
}


def dataframe_codec() -> ValueCodec:
    pandas = import_module("pandas")

    return ValueCodec(pandas.DataFrame, _SCHEMA, _encode, _decode)


def series_codec() -> ValueCodec:
    pandas = import_module("pandas")

    return ValueCodec(pandas.Series, _SCHEMA, _encode, _decode)


def _require_arrow() -> Any:
    try:
        return import_module("pyarrow")
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ValueError(
            "sending pandas values requires pyarrow (pip install pyarrow); "
            "it preserves dtypes and the index exactly, which CSV and JSON do not"
        ) from exc


def _encode(value: Any) -> dict[str, Any]:
    pandas = import_module("pandas")
    pyarrow = _require_arrow()

    is_series = isinstance(value, pandas.Series)
    frame = value.to_frame() if is_series else value
    # `preserve_index=True` keeps a non-default index, which callers routinely
    # rely on as data rather than as presentation.
    table = pyarrow.Table.from_pandas(frame, preserve_index=True)
    sink = io.BytesIO()
    with pyarrow.ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    raw = sink.getvalue()
    if len(raw) > MAX_FRAME_BYTES:
        raise ValueError(
            "pandas value exceeds value codec limits; use chunked transfer"
        )
    encoded: dict[str, Any] = {
        "kind": "series" if is_series else "frame",
        "data": base64.b64encode(raw).decode("ascii"),
    }
    if is_series:
        encoded["name"] = value.name if isinstance(value.name, str) else None
    return encoded


def _decode(value: Any) -> Any:
    pyarrow = _require_arrow()

    if not isinstance(value, dict) or not {"kind", "data"} <= set(value):
        raise ValueError("invalid pandas envelope")
    if value["kind"] not in {"frame", "series"}:
        raise ValueError("invalid pandas envelope kind")
    data = value["data"]
    if not isinstance(data, str) or len(data) > ((MAX_FRAME_BYTES + 2) // 3) * 4:
        raise ValueError("pandas payload exceeds limit")
    raw = base64.b64decode(data, validate=True)
    if len(raw) > MAX_FRAME_BYTES:
        raise ValueError("pandas payload exceeds limit")
    with pyarrow.ipc.open_stream(io.BytesIO(raw)) as reader:
        frame = reader.read_all().to_pandas()
    if value["kind"] == "frame":
        return frame
    series = frame[frame.columns[0]]
    name = value.get("name")
    return series.rename(name) if isinstance(name, str) else series.rename(None)
