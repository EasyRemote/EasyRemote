#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest

from easyremote.core.data.backends import JSONBackend, PickleBackend
from easyremote.core.data.config import CompressionAlgorithm
from easyremote.core.utils.exceptions import SerializationError


def test_pickle_backend_roundtrip_with_gzip_compression():
    backend = PickleBackend(
        compress=True,
        compression_algorithm=CompressionAlgorithm.GZIP,
        compression_level=6,
    )
    payload = {"numbers": [1, 2, 3], "nested": {"ok": True}}

    blob = backend.serialize(payload)

    assert isinstance(blob, bytes)
    assert backend.deserialize(blob) == payload


def test_json_backend_roundtrip_for_extended_types():
    backend = JSONBackend()
    payload = {
        "tuple": (1, 2),
        "set": {"a", "b"},
        "complex": 1 + 2j,
        "bytes": b"ab",
    }

    encoded = backend.serialize(payload)
    decoded = backend.deserialize(encoded)

    assert decoded["tuple"] == (1, 2)
    assert decoded["set"] == {"a", "b"}
    assert decoded["complex"] == 1 + 2j
    assert decoded["bytes"] == b"ab"


def test_pickle_backend_invalid_data_raises_serialization_error():
    backend = PickleBackend(compress=False, safe_mode=True)

    with pytest.raises(SerializationError):
        backend.deserialize(b"not-a-pickle-payload")
