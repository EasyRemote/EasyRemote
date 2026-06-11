"""Argument/result fidelity codec for the warm host.

JSON carries the wire; annotations carry the intent. Parameters are
rehydrated to their annotated Python types — dataclasses, pydantic
models, tuples, sets, enums, bytes, through nested containers and
Optionals — before the function runs, and results are lowered back to
JSON-able values symmetrically. A function written against rich types
works unchanged across the network.

Deliberate limits: unions beyond Optional are tried arm-by-arm and
fall back to the raw value; arbitrary classes were already rejected at
registration (SchemaError), so they cannot reach here.
"""

from __future__ import annotations

import base64
import dataclasses
import enum
import types
import typing
from collections.abc import Mapping, Sequence
from typing import Any, Union

__all__ = ["rehydrate", "to_jsonable"]

_EMPTY = object()


def rehydrate(value: Any, annotation: Any = _EMPTY) -> Any:
    """Lift a JSON value to its annotated Python type."""
    if annotation is _EMPTY or annotation is Any or value is None:
        return value

    if annotation is bytes:
        return base64.b64decode(value) if isinstance(value, str) else value

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin in (Union, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        for arm in non_none:
            try:
                return rehydrate(value, arm)
            except Exception:
                continue
        return value
    if origin is tuple and isinstance(value, Sequence):
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(rehydrate(item, args[0]) for item in value)
        if args:
            return tuple(
                rehydrate(item, arm) for item, arm in zip(value, args, strict=False)
            )
        return tuple(value)
    if origin in (set, frozenset) and isinstance(value, Sequence):
        rebuilt = (rehydrate(item, args[0]) if args else item for item in value)
        return frozenset(rebuilt) if origin is frozenset else set(rebuilt)
    if origin in (list, Sequence) and isinstance(value, list):
        return [rehydrate(item, args[0]) if args else item for item in value]
    if origin in (dict, Mapping) and isinstance(value, dict):
        if len(args) == 2:
            return {key: rehydrate(item, args[1]) for key, item in value.items()}
        return value

    if isinstance(annotation, type):
        if issubclass(annotation, enum.Enum):
            return annotation(value)
        if dataclasses.is_dataclass(annotation) and isinstance(value, dict):
            hints = typing.get_type_hints(annotation)
            return annotation(
                **{
                    key: rehydrate(item, hints.get(key, _EMPTY))
                    for key, item in value.items()
                }
            )
        validate = getattr(annotation, "model_validate", None)
        if callable(validate) and isinstance(value, dict):  # pydantic v2
            return validate(value)

    return value


def to_jsonable(value: Any) -> Any:
    """Lower a rich Python value to JSON-able form (mirror of rehydrate)."""
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, enum.Enum):
        return to_jsonable(value.value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    dump = getattr(value, "model_dump", None)
    if callable(dump):  # pydantic v2
        return dump(mode="json")
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return value
