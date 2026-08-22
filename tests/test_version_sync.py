"""Release-version synchronization contracts."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "_version_sync.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("easyremote_version_sync", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fixture(tmp_path: Path) -> Path:
    package = tmp_path / "easyremote"
    package.mkdir()
    (package / "_version.py").write_text(
        '__version__ = "2.1.0a1"\n', encoding="utf-8"
    )
    (package / "edge-adapter-policy.v1.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "package": {
                    "name": "easyremote",
                    "current_version": "2.1.0a1",
                },
                "removal_version": "3.0.0",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_synchronizer_converges_all_projections(tmp_path: Path) -> None:
    module = _load_script()
    root = _fixture(tmp_path)
    synchronizer = module.ProjectVersionSynchronizer(root)

    assert len(synchronizer.drift("2.190.3")) == 2
    changed = synchronizer.synchronize("2.190.3")

    assert len(changed) == 2
    assert synchronizer.current_version() == "2.190.3"
    assert synchronizer.drift("2.190.3") == ()


def test_invalid_version_is_read_only(tmp_path: Path) -> None:
    module = _load_script()
    root = _fixture(tmp_path)
    before = {
        path: path.read_bytes() for path in (root / "easyremote").iterdir()
    }

    with pytest.raises(ValueError, match="invalid Tide/PEP 440 version"):
        module.ProjectVersionSynchronizer(root).synchronize("latest")

    assert {path: path.read_bytes() for path in before} == before


def test_failed_replacement_restores_previous_files(tmp_path: Path) -> None:
    module = _load_script()
    root = _fixture(tmp_path)
    targets = tuple(sorted((root / "easyremote").iterdir()))
    before = {path: path.read_bytes() for path in targets}
    replacements = 0

    def fail_on_second_replacement(source: Path, target: Path) -> None:
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("injected replacement failure")
        module._replace_file(source, target)

    synchronizer = module.ProjectVersionSynchronizer(
        root, replace_file=fail_on_second_replacement
    )
    with pytest.raises(OSError, match="injected replacement failure"):
        synchronizer.synchronize("2.190.3")

    assert {path: path.read_bytes() for path in targets} == before
