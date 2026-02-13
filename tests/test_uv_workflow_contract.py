#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Contract tests for uv-based development and test workflow.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

from pathlib import Path


def _iter_non_comment_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def test_root_makefile_uses_uv_for_sync_and_tests() -> None:
    project_root = Path(__file__).resolve().parents[1]
    makefile = project_root / "Makefile"
    content = makefile.read_text(encoding="utf-8")

    assert "uv sync" in content
    assert "uv run pytest -q" in content
    assert "uv run python gallery/run_smoke_tests.py" in content


def test_gallery_makefiles_do_not_use_raw_python_commands() -> None:
    project_root = Path(__file__).resolve().parents[1]
    makefiles = [
        project_root / "gallery/Makefile",
        project_root / "gallery/projects/00_basic_remote_math/Makefile",
        project_root / "gallery/projects/01_team_gpu_pool_load_balancing/Makefile",
        project_root / "gallery/projects/02_mcp_tool_mesh/Makefile",
        project_root / "gallery/projects/03_a2a_incident_copilot/Makefile",
        project_root / "gallery/projects/04_function_marketplace/Makefile",
        project_root / "gallery/projects/05_local_data_residency_ai/Makefile",
        project_root / "gallery/projects/06_runtime_device_capability_injection/Makefile",
    ]

    violations: list[str] = []
    for path in makefiles:
        for line in _iter_non_comment_lines(path.read_text(encoding="utf-8")):
            if "python" in line and "uv run python" not in line:
                violations.append(f"{path}:{line}")

    assert not violations, (
        "Found non-uv python commands in gallery makefiles: "
        + "; ".join(violations)
    )


def test_gallery_smoke_runner_prefers_uv_for_subprocess_execution() -> None:
    project_root = Path(__file__).resolve().parents[1]
    smoke_runner = project_root / "gallery/run_smoke_tests.py"
    content = smoke_runner.read_text(encoding="utf-8")

    assert 'shutil.which("uv")' in content
    assert '("uv", "run", "--no-sync", "python")' in content
