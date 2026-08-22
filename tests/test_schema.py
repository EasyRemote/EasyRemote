"""Schema derivation: the SPEC §5.4 rule table, row by row."""

import enum
import warnings
from dataclasses import dataclass
from typing import Any, Literal

import pytest

from easyremote.errors import SchemaError
from easyremote.schema import PARAMETER_ORDER_KEY, derive


def props(sig):
    return sig.input_schema["properties"]


# -- scalars and containers --------------------------------------------------


def test_scalars():
    def fn(a: str, b: int, c: float, d: bool, e: bytes) -> str: ...

    sig = derive(fn)
    assert props(sig) == {
        "a": {"type": "string"},
        "b": {"type": "integer"},
        "c": {"type": "number"},
        "d": {"type": "boolean"},
        "e": {"type": "string", "contentEncoding": "base64"},
    }
    assert sig.input_schema["required"] == ["a", "b", "c", "d", "e"]
    assert sig.output_schema == {"type": "string"}
    assert not sig.is_stream


def test_generic_containers():
    def fn(xs: list[int], m: dict[str, float], t: tuple[str, int]) -> None: ...

    sig = derive(fn)
    assert props(sig)["xs"] == {"type": "array", "items": {"type": "integer"}}
    assert props(sig)["m"] == {
        "type": "object",
        "additionalProperties": {"type": "number"},
    }
    assert props(sig)["t"]["prefixItems"] == [{"type": "string"}, {"type": "integer"}]


def test_bare_containers_and_any():
    def fn(xs: list, m: dict, a: Any) -> None: ...

    sig = derive(fn)
    assert props(sig)["xs"] == {"type": "array"}
    assert props(sig)["m"] == {"type": "object"}
    assert props(sig)["a"] == {}


def test_optional_and_union():
    def fn(a: int | None, b: str | int) -> None: ...

    sig = derive(fn)
    assert {"type": "null"} in props(sig)["a"]["anyOf"]
    assert {"type": "integer"} in props(sig)["a"]["anyOf"]
    assert len(props(sig)["b"]["anyOf"]) == 2


def test_typing_optional_spelling():
    def fn(a: int | None) -> None: ...

    assert {"type": "null"} in props(derive(fn))["a"]["anyOf"]


def test_literal():
    def fn(mode: Literal["fast", "slow"]) -> None: ...

    assert props(derive(fn))["mode"] == {"enum": ["fast", "slow"]}


# -- structured types ---------------------------------------------------------


def test_dataclass_expansion():
    @dataclass
    class Job:
        name: str
        priority: int = 0

    def fn(job: Job) -> None: ...

    schema = props(derive(fn))["job"]
    assert schema["properties"]["name"] == {"type": "string"}
    assert schema["required"] == ["name"]  # priority has a default


def test_enum_values():
    class Color(enum.Enum):
        RED = "red"
        BLUE = "blue"

    def fn(c: Color) -> None: ...

    assert props(derive(fn))["c"] == {"enum": ["red", "blue"]}


def test_pydantic_model_via_duck_typing():
    class FakeModel:
        @classmethod
        def model_json_schema(cls):
            return {"type": "object", "title": "FakeModel"}

    def fn(m: FakeModel) -> None: ...

    assert props(derive(fn))["m"]["title"] == "FakeModel"


# -- defaults, ordering, permissive mode --------------------------------------


def test_defaults_are_not_required():
    def fn(a: str, b: int = 3) -> None: ...

    sig = derive(fn)
    assert sig.input_schema["required"] == ["a"]
    assert sig.input_schema[PARAMETER_ORDER_KEY] == ["a", "b"]


def test_non_finite_default_is_not_advertised():
    def fn(a: float = float("inf")) -> None: ...

    assert "default" not in props(derive(fn))["a"]


def test_unannotated_parameter_warns_and_is_permissive():
    def fn(a): ...

    with pytest.warns(UserWarning, match="no type annotation"):
        sig = derive(fn)
    assert props(sig)["a"] == {}


# -- rejections ----------------------------------------------------------------


def test_custom_class_rejected_with_three_exits():
    class Opaque: ...

    def fn(x: Opaque) -> None: ...

    with pytest.raises(SchemaError) as exc_info:
        derive(fn)
    message = str(exc_info.value)
    assert "Opaque" in message
    for exit_marker in ("(1)", "(2)", "(3)"):
        assert exit_marker in message


def test_var_positional_becomes_array_param():
    def fn(*nums: int) -> None: ...

    sig = derive(fn)
    from easyremote.schema import VAR_POSITIONAL_KEY

    assert sig.input_schema["properties"]["nums"] == {
        "type": "array",
        "items": {"type": "integer"},
    }
    assert sig.input_schema[VAR_POSITIONAL_KEY] == "nums"
    # *args is variadic, never required.
    assert "nums" not in sig.input_schema.get("required", [])


def test_var_keyword_opens_additional_properties():
    def fn(base: int, **extra: str) -> None: ...

    sig = derive(fn)
    # **kwargs opens the object; its value schema is the annotation.
    assert sig.input_schema["additionalProperties"] == {"type": "string"}
    assert sig.input_schema["required"] == ["base"]
    # The **kwargs parameter itself is not a named property.
    assert "extra" not in sig.input_schema["properties"]


def test_non_string_dict_keys_rejected():
    def fn(m: dict[int, str]) -> None: ...

    with pytest.raises(SchemaError, match="keys must be str"):
        derive(fn)


# -- streams -------------------------------------------------------------------


def test_generator_is_stream_with_chunk_schema():
    from collections.abc import Iterator

    def fn(n: int) -> Iterator[str]:
        yield "chunk"

    sig = derive(fn)
    assert sig.is_stream
    assert sig.output_schema == {"type": "string"}


def test_async_generator_is_stream():
    from collections.abc import AsyncIterator

    async def fn(n: int) -> AsyncIterator[bytes]:
        yield b""

    assert derive(fn).is_stream


def test_ordinary_function_returning_iterator_is_stream():
    from collections.abc import Iterator

    def fn(n: int) -> Iterator[int]:
        return iter(range(n))

    signature = derive(fn)
    assert signature.is_stream
    assert signature.output_schema == {"type": "integer"}


def test_typed_media_generator_declares_dynamic_binary_frames():
    from collections.abc import Iterator

    from easyremote import StreamFrame

    def fn() -> Iterator[StreamFrame]:
        yield StreamFrame(b"jpeg", "image/jpeg")

    assert derive(fn).output_schema == {
        "type": "string",
        "contentEncoding": "binary",
        "x-easyremote-dynamic-content-type": True,
    }


# -- context injection ----------------------------------------------------------


def test_context_first_param_skipped():
    class Ctx: ...

    def fn(ctx: Ctx, prompt: str) -> str: ...

    sig = derive(fn, context_type=Ctx)
    assert sig.takes_context
    assert list(props(sig)) == ["prompt"]
    assert sig.input_schema[PARAMETER_ORDER_KEY] == ["prompt"]


def test_context_type_not_given_means_plain_param():
    class Ctx: ...

    def fn(ctx: Ctx, prompt: str) -> str: ...

    with pytest.raises(SchemaError):  # Ctx is then just an opaque class
        derive(fn)


def test_context_on_non_first_param_rejected():
    class Ctx: ...

    def fn(prompt: str, ctx: Ctx) -> str: ...

    with pytest.raises(SchemaError, match="must be the first parameter"):
        derive(fn, context_type=Ctx)


def test_no_warning_for_fully_annotated():
    def fn(a: int) -> int: ...

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        derive(fn)
