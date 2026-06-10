"""Type-hint → JSON Schema derivation (SPEC §5.4).

``derive()`` turns a Python callable into the schema half of an
``AbilityManifest``: an ``input_schema`` the daemon enforces at call
time, an optional ``output_schema``, plus stream/context markers. The
rules are exactly the SPEC §5.4 table — anything outside it raises
:class:`SchemaError` at registration time so users never discover an
unserializable parameter in production.

Validation against these schemas happens daemon-side; this module only
*produces* schemas.
"""

from __future__ import annotations

import dataclasses
import enum
import inspect
import json
import types
import typing
import warnings
from collections.abc import (
    AsyncGenerator,
    AsyncIterable,
    AsyncIterator,
    Generator,
    Iterable,
    Iterator,
    Mapping,
    Sequence,
)
from dataclasses import dataclass
from typing import Any, Literal, Union

from .errors import SchemaError

__all__ = ["DerivedSignature", "derive"]

# JSON Schema extension carrying positional-call order. JSON object key
# order is not contractual, so the explicit list is what lets a client
# map `execute("fn", a, b)` onto named parameters.
PARAMETER_ORDER_KEY = "x-easyremote-parameter-order"

_SCALARS: dict[type, dict[str, Any]] = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    bytes: {"type": "string", "contentEncoding": "base64"},
    type(None): {"type": "null"},
}

_BARE_CONTAINERS: dict[type, dict[str, Any]] = {
    list: {"type": "array"},
    tuple: {"type": "array"},
    dict: {"type": "object"},
    Sequence: {"type": "array"},
    Iterable: {"type": "array"},
    Mapping: {"type": "object"},
}

_STREAM_ORIGINS = (
    Generator,
    Iterator,
    Iterable,
    AsyncGenerator,
    AsyncIterator,
    AsyncIterable,
)


@dataclass(frozen=True)
class DerivedSignature:
    """Everything node-side registration needs from a function signature."""

    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    is_stream: bool
    takes_context: bool


def derive(fn: Any, *, context_type: type | None = None) -> DerivedSignature:
    """Derive ability schemas from ``fn``'s signature.

    Args:
        fn: The function being registered.
        context_type: When given, a first parameter annotated with this
            exact type is treated as the injected server-side
            :class:`~easyremote.Context` and excluded from the schema.

    Raises:
        SchemaError: for signatures outside the SPEC §5.4 table
            (variadics, non-JSON-representable annotations).
    """
    signature = inspect.signature(fn)
    hints = _type_hints(fn)
    name = getattr(fn, "__name__", str(fn))

    parameters = list(signature.parameters.values())
    takes_context = _takes_context(parameters, hints, context_type)
    if takes_context:
        parameters = parameters[1:]

    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []
    for parameter in parameters:
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            raise SchemaError(
                f"'{name}' declares *{parameter.name} — capabilities need explicit"
                " parameters so callers and the daemon share one schema"
            )
        annotation = hints.get(parameter.name, parameter.annotation)
        if annotation is inspect.Parameter.empty:
            warnings.warn(
                f"parameter '{parameter.name}' of '{name}' has no type annotation;"
                " using a permissive schema — annotate it for daemon-side validation",
                UserWarning,
                stacklevel=3,
            )
            schema: dict[str, Any] = {}
        else:
            schema = _to_schema(annotation, name, parameter.name)
        if parameter.default is inspect.Parameter.empty:
            required.append(parameter.name)
        else:
            schema = _with_default(schema, parameter.default)
        properties[parameter.name] = schema

    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
        PARAMETER_ORDER_KEY: [p.name for p in parameters],
    }
    if required:
        input_schema["required"] = required

    is_stream = inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn)
    output_schema = _output_schema(
        hints.get("return", inspect.Parameter.empty), name, is_stream
    )
    return DerivedSignature(
        input_schema=input_schema,
        output_schema=output_schema,
        is_stream=is_stream,
        takes_context=takes_context,
    )


def _with_default(schema: dict[str, Any], default: Any) -> dict[str, Any]:
    """Record a JSON-representable default on the property schema.

    Lets remote callers (and the facade client) fill omitted optionals
    from discovery alone. Non-JSON defaults are simply not advertised.
    """
    try:
        json.dumps(default)
    except (TypeError, ValueError):
        return schema
    enriched = dict(schema)
    enriched["default"] = default
    return enriched


def _type_hints(fn: Any) -> dict[str, Any]:
    try:
        return typing.get_type_hints(fn)
    except Exception:
        # Unresolvable forward references degrade to "unannotated", which
        # the per-parameter loop reports with a UserWarning.
        return {}


def _takes_context(
    parameters: list[inspect.Parameter],
    hints: dict[str, Any],
    context_type: type | None,
) -> bool:
    if context_type is None or not parameters:
        return False
    first = parameters[0]
    return hints.get(first.name, first.annotation) is context_type


def _output_schema(
    annotation: Any, fn_name: str, is_stream: bool
) -> dict[str, Any] | None:
    if annotation is inspect.Parameter.empty or annotation is None:
        return None
    if is_stream:
        chunk = _stream_chunk_type(annotation)
        if chunk is None:
            return None
        return _to_schema(chunk, fn_name, "<yield>")
    return _to_schema(annotation, fn_name, "<return>")


def _stream_chunk_type(annotation: Any) -> Any | None:
    origin = typing.get_origin(annotation)
    if origin in _STREAM_ORIGINS:
        args = typing.get_args(annotation)
        return args[0] if args else None
    return None


def _to_schema(annotation: Any, fn_name: str, param_name: str) -> dict[str, Any]:
    if annotation is Any:
        return {}
    if annotation in _SCALARS:
        return dict(_SCALARS[annotation])
    if annotation in _BARE_CONTAINERS:
        return dict(_BARE_CONTAINERS[annotation])

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is Literal:
        for member in args:
            if not isinstance(member, (str, int, bool)) and member is not None:
                raise _unsupported(annotation, fn_name, param_name)
        return {"enum": list(args)}
    if origin in (Union, types.UnionType):
        return {"anyOf": [_to_schema(a, fn_name, param_name) for a in args]}
    if origin in (list, Sequence, Iterable, set, frozenset):
        item = _to_schema(args[0], fn_name, param_name) if args else {}
        return {"type": "array", "items": item}
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return {"type": "array", "items": _to_schema(args[0], fn_name, param_name)}
        return {
            "type": "array",
            "prefixItems": [_to_schema(a, fn_name, param_name) for a in args],
            "minItems": len(args),
            "maxItems": len(args),
        }
    if origin in (dict, Mapping):
        if args and args[0] is not str:
            raise SchemaError(
                f"parameter '{param_name}' of '{fn_name}': JSON object keys must be"
                f" str, not {_describe(args[0])}"
            )
        value = _to_schema(args[1], fn_name, param_name) if args else {}
        return {"type": "object", "additionalProperties": value}

    if isinstance(annotation, type):
        if issubclass(annotation, enum.Enum):
            return _enum_schema(annotation, fn_name, param_name)
        if dataclasses.is_dataclass(annotation):
            return _dataclass_schema(annotation, fn_name, param_name)
        model_schema = getattr(annotation, "model_json_schema", None)
        if callable(model_schema):  # pydantic v2 BaseModel, without importing it
            return dict(model_schema())

    raise _unsupported(annotation, fn_name, param_name)


def _enum_schema(
    annotation: type[enum.Enum], fn_name: str, param_name: str
) -> dict[str, Any]:
    values = [member.value for member in annotation]
    if not all(isinstance(v, (str, int)) for v in values):
        raise _unsupported(annotation, fn_name, param_name)
    return {"enum": values}


def _dataclass_schema(
    annotation: type, fn_name: str, param_name: str
) -> dict[str, Any]:
    hints = typing.get_type_hints(annotation)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field in dataclasses.fields(annotation):
        properties[field.name] = _to_schema(
            hints.get(field.name, field.type), fn_name, f"{param_name}.{field.name}"
        )
        if (
            field.default is dataclasses.MISSING
            and field.default_factory is dataclasses.MISSING
        ):
            required.append(field.name)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _unsupported(annotation: Any, fn_name: str, param_name: str) -> SchemaError:
    return SchemaError(
        f"parameter '{param_name}' of '{fn_name}' has annotation"
        f" {_describe(annotation)}, which cannot become a JSON schema. Either"
        " (1) annotate with JSON-representable types, (2) model it as a"
        " dataclass or pydantic.BaseModel, or (3) pass binary data as `bytes`"
        " with an explicit content_type."
    )


def _describe(annotation: Any) -> str:
    if isinstance(annotation, type):
        return annotation.__qualname__
    return repr(annotation)
