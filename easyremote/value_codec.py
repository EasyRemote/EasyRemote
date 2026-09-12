"""Explicit Python value codecs shared by schema, caller and provider.

Register the same codec on both endpoints before declaring abilities. Wire
values never select or import Python classes; local annotations select decoders.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any

from ._json import dumps_wire


@dataclass(frozen=True)
class ValueCodec:
    """One value type's JSON schema and inverse conversion functions."""

    python_type: type
    schema: dict[str, Any]
    encode: Callable[[Any], Any]
    decode: Callable[[Any], Any]


_codecs: dict[type, ValueCodec] = {}
_lock = RLock()


def register_value_codec(codec: ValueCodec) -> None:
    """Register once at process setup; conflicting registrations fail."""
    if not isinstance(codec.python_type, type):
        raise TypeError("codec python_type must be a class")
    if not isinstance(codec.schema, dict):
        raise TypeError("codec schema must be a JSON schema object")
    if not callable(codec.encode) or not callable(codec.decode):
        raise TypeError("codec encode and decode must be callable")
    dumps_wire(codec.schema, what="value codec schema")
    with _lock:
        if codec.python_type in _codecs:
            raise ValueError(
                f"codec already registered for {codec.python_type.__name__}"
            )
        _codecs[codec.python_type] = ValueCodec(
            codec.python_type, deepcopy(codec.schema), codec.encode, codec.decode
        )


def codec_for(annotation: Any) -> ValueCodec | None:
    if not isinstance(annotation, type):
        return None
    with _lock:
        codec = _codecs.get(annotation)
    if codec is not None:
        return codec
    # Optional NumPy support without importing a missing optional dependency.
    if annotation.__module__ == "numpy" and annotation.__name__ == "ndarray":
        from ._numpy_codec import array_codec

        return array_codec()
    return _optional_codec_for(annotation)


# Built-in codecs for widely used scientific types. Each is resolved by module
# and class name so an absent library is simply never imported, and each is
# consulted only after explicit registrations, so a caller can still override
# one for their own wire shape.
_OPTIONAL_CODECS: dict[tuple[str, str], str] = {
    ("torch", "Tensor"): "_torch_codec",
    ("pandas.core.frame", "DataFrame"): "_pandas_codec",
    ("pandas.core.series", "Series"): "_pandas_codec",
    ("PIL.Image", "Image"): "_pillow_codec",
}

_OPTIONAL_FACTORIES: dict[tuple[str, str], str] = {
    ("torch", "Tensor"): "tensor_codec",
    ("pandas.core.frame", "DataFrame"): "dataframe_codec",
    ("pandas.core.series", "Series"): "series_codec",
    ("PIL.Image", "Image"): "image_codec",
}


def _optional_codec_for(annotation: type) -> ValueCodec | None:
    key = (annotation.__module__, annotation.__name__)
    module_name = _OPTIONAL_CODECS.get(key)
    if module_name is None:
        # Subclasses keep their library's wire shape: `torch.nn.Parameter` is a
        # Tensor and must not fall through to the generic object encoder, which
        # would lose its dtype and values.
        for (module, name), candidate in _OPTIONAL_CODECS.items():
            base = _loaded_class(module, name)
            if base is not None and issubclass(annotation, base):
                module_name = candidate
                key = (module, name)
                break
        if module_name is None:
            return None
    from importlib import import_module

    factory = getattr(
        import_module(f".{module_name}", __package__), _OPTIONAL_FACTORIES[key]
    )
    return factory()


def _loaded_class(module: str, name: str) -> type | None:
    """Resolve a class only if its module is already imported.

    Importing here would turn an optional dependency into a load-time cost for
    every annotation this function sees. If the caller holds an instance, the
    module is necessarily imported already.
    """
    import sys

    loaded = sys.modules.get(module)
    if loaded is None:
        return None
    candidate = getattr(loaded, name, None)
    return candidate if isinstance(candidate, type) else None
