"""TOML serializer: round-trips through stdlib tomllib."""

import pytest
import tomllib

from easyremote import _toml


def round_trip(document):
    return tomllib.loads(_toml.dumps(document))


def test_manifest_shaped_document_round_trips():
    document = {
        "schema_version": "1",
        "name": "weather",
        "description": "fetch weather",
        "timeout_seconds": 30,
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "days": {"type": "integer", "default": 3},
            },
            "additionalProperties": False,
            "x-easyremote-parameter-order": ["location", "days"],
            "required": ["location", "days"],
        },
        "exec": {
            "kind": "shell",
            "argv": ["curl", "-s", "https://example/{{ location }}"],
        },
    }
    assert round_trip(document) == document


def test_quoted_keys_and_unicode():
    document = {"input_schema": {"x-easyremote-parameter-order": [], "描述": "中文"}}
    assert round_trip(document) == document


def test_scalars_arrays_and_inline_tables():
    document = {
        "flags": {"a": True, "b": False},
        "nums": {"i": 3, "f": 1.5},
        "nested": {"prefixItems": [{"type": "string"}, {"type": "integer"}]},
    }
    assert round_trip(document) == document


def test_scalar_after_subtable_stays_in_right_table():
    # Emission order bug-trap: scalars must precede [sub] headers.
    document = {"outer": {"sub": {"x": 1}, "y": 2}}
    assert round_trip(document) == document


def test_unsupported_value_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        _toml.dumps({"bad": object()})
