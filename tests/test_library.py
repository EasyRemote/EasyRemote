"""Network-native library manifests and local Python projections."""

from __future__ import annotations

import importlib
import inspect
import json
import sys
from pathlib import Path

import pytest
from conftest import expected_descriptor_ref

from easyremote import (
    LibraryManifest,
    install_library,
    list_libraries,
    remove_library,
)
from easyremote.errors import InvalidArgument

ABILITY_URA = (
    "easynet:///r/acme/ability/"
    "system-agent.dev-a.ability-management.lotus.semantic_filter"
)


def _manifest(**overrides: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "format": "easyremote.library/v1",
        "realm": "easynet.run",
        "publisher": "acme",
        "package": "lotus",
        "version": "1.2.3",
        "exports": [
            {
                "python_name": "semantic_filter",
                "ability": ABILITY_URA,
                "description": "Filter records remotely.",
                "descriptor_ref": expected_descriptor_ref(
                    ABILITY_URA,
                    version="1.2.3",
                ),
                "call_mode": "rpc",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "records": {"type": "array", "items": {"type": "string"}},
                        "condition": {"type": "string"},
                    },
                    "required": ["records", "condition"],
                    "x-easyremote-parameter-order": ["records", "condition"],
                },
                "output_schema": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            }
        ],
    }
    manifest.update(overrides)
    return manifest


def _write_manifest(path: Path, **overrides: object) -> Path:
    path.write_text(json.dumps(_manifest(**overrides)), encoding="utf-8")
    return path


def test_manifest_has_scoped_coordinate_and_native_import() -> None:
    manifest = LibraryManifest.from_mapping(_manifest())

    assert manifest.coordinate == "@acme/lotus@1.2.3"
    assert manifest.realm == "easynet.run"
    assert manifest.default_import == "easyremote.acme.lotus"


def test_install_materializes_only_a_typed_interface(tmp_path: Path) -> None:
    projection = tmp_path / "projection"
    source = _write_manifest(tmp_path / "library.json")
    installed = install_library(source, root=projection)

    assert installed.import_name == "easyremote.acme.lotus"
    assert {item.name for item in installed.path.iterdir()} == {
        "__init__.py",
        "__init__.pyi",
        "easyremote-library.lock.json",
        "py.typed",
    }
    generated = (installed.path / "__init__.py").read_text(encoding="utf-8")
    assert "@remote(" in generated
    descriptor_ref = expected_descriptor_ref(ABILITY_URA, version="1.2.3")
    assert f"descriptor_ref={descriptor_ref!r}" in generated
    assert "def semantic_filter(" in generated
    assert "def _terms" not in generated

    sys.modules.pop("easyremote.acme.lotus", None)
    sys.modules.pop("easyremote.acme", None)
    module = importlib.import_module(installed.import_name)
    assert str(inspect.signature(module.semantic_filter)) == (
        "(records: 'list[str]', condition: 'str') -> 'list[str]'"
    )
    assert module.__easyremote_coordinate__ == "@acme/lotus@1.2.3"


def test_alias_list_and_remove_are_exact(tmp_path: Path) -> None:
    source = _write_manifest(tmp_path / "library.json")
    installed = install_library(source, root=tmp_path / "projection", alias="lotus")

    assert installed.import_name == "easyremote.lotus"
    assert list_libraries(root=tmp_path / "projection") == (installed,)
    removed = remove_library(installed.import_name, root=tmp_path / "projection")
    assert removed == installed
    assert not installed.path.exists()
    assert list_libraries(root=tmp_path / "projection") == ()


@pytest.mark.parametrize(
    "field,value", [("publisher", "bad-name"), ("version", "^1.2")]
)
def test_manifest_fails_closed_on_non_importable_or_floating_identity(
    field: str, value: str
) -> None:
    with pytest.raises(InvalidArgument):
        LibraryManifest.from_mapping(_manifest(**{field: value}))


@pytest.mark.parametrize("call_mode", ["stream", "bidi"])
def test_manifest_rejects_unimplemented_library_call_modes(call_mode: str) -> None:
    exports = list(_manifest()["exports"])
    exports[0] = {**exports[0], "call_mode": call_mode, "descriptor_ref": ""}

    with pytest.raises(InvalidArgument) as exc_info:
        LibraryManifest.from_mapping(_manifest(exports=exports))

    assert exc_info.value.reason == "invalid_library_call_mode"


def test_manifest_rejects_invalid_or_mismatched_descriptor_refs() -> None:
    exports = list(_manifest()["exports"])
    exports[0] = {**exports[0], "descriptor_ref": "descriptor:lotus-filter-v1"}
    with pytest.raises(InvalidArgument) as invalid:
        LibraryManifest.from_mapping(_manifest(exports=exports))
    assert invalid.value.reason == "invalid_library_descriptor_ref"

    other_ability = ABILITY_URA.replace("semantic_filter", "semantic_map")
    exports[0] = {
        **exports[0],
        "descriptor_ref": expected_descriptor_ref(other_ability),
    }
    with pytest.raises(InvalidArgument) as mismatch:
        LibraryManifest.from_mapping(_manifest(exports=exports))
    assert mismatch.value.reason == "library_descriptor_ability_mismatch"
