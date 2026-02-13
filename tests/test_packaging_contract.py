#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for package layering and version management contracts.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from pathlib import Path

import pytest

from easyremote import __version__ as public_version
from easyremote._version import __version__ as internal_version


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"


def _load_pyproject() -> dict:
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:  # pragma: no cover
        tomllib = pytest.importorskip("tomli")

    return tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))


def test_version_is_single_sourced_via_easyremote_version_module():
    pyproject = _load_pyproject()
    project = pyproject["project"]

    assert project.get("dynamic") == ["version"]
    assert (
        pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"]
        == "easyremote._version.__version__"
    )
    assert public_version == internal_version


def test_core_dependencies_exclude_optional_build_and_gpu_packages():
    pyproject = _load_pyproject()
    deps = pyproject["project"]["dependencies"]
    joined = "\n".join(deps).lower()

    assert "grpcio-tools" not in joined
    assert "gputil" not in joined


def test_optional_extensions_include_build_and_gpu():
    pyproject = _load_pyproject()
    optional = pyproject["project"]["optional-dependencies"]

    assert "build" in optional
    assert any("grpcio-tools" in dep.lower() for dep in optional["build"])

    assert "gpu" in optional
    assert any("gputil" in dep.lower() for dep in optional["gpu"])


def test_uv_default_groups_cover_dev_and_test():
    pyproject = _load_pyproject()
    groups = pyproject["dependency-groups"]
    default_groups = pyproject["tool"]["uv"]["default-groups"]

    assert "dev" in groups
    assert "test" in groups
    assert "dev" in default_groups
    assert "test" in default_groups

