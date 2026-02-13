#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Contract tests for GitHub publish workflow.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

from pathlib import Path


def test_publish_workflow_targets_main_branch() -> None:
    project_root = Path(__file__).resolve().parents[1]
    workflow = project_root / ".github/workflows/publish-easyremote.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "branches: [main]" in content
    assert "name: Publish easyremote to PyPI" in content
    assert '"easyremote/_version.py"' in content


def test_publish_workflow_uses_uv_quality_gate() -> None:
    project_root = Path(__file__).resolve().parents[1]
    workflow = project_root / ".github/workflows/publish-easyremote.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "uv sync --frozen" in content
    assert "uvx ruff check" in content
    assert "uv run pytest -q" in content
    assert "uv build" in content
    assert "uvx --from twine twine check dist/*" in content


def test_publish_workflow_uses_trusted_publishing() -> None:
    project_root = Path(__file__).resolve().parents[1]
    workflow = project_root / ".github/workflows/publish-easyremote.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "id-token: write" in content
    assert "pypa/gh-action-pypi-publish@release/v1" in content
    assert "environment:" in content
    assert "name: pypi" in content
    assert "skip-existing: true" in content
