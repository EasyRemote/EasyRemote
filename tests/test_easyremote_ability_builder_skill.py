from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
SKILL = ROOT / "skills" / "easyremote-ability-builder"
SCAFFOLD = SKILL / "scripts" / "scaffold_case.py"


def test_skill_has_discoverable_metadata_and_required_references() -> None:
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    assert skill.startswith("---\nname: easyremote-ability-builder\n")
    assert "@node.register" in skill
    assert "@remote" in skill
    assert "references/api-patterns.md" in skill
    assert "references/diagnostics.md" in skill
    assert (SKILL / "agents" / "openai.yaml").is_file()


def test_scaffold_creates_unary_and_stream_uv_projects(tmp_path: Path) -> None:
    for name, extra in (("score_signal", []), ("watch_signal", ["--stream"])):
        destination = tmp_path / name
        subprocess.run(
            [
                sys.executable,
                str(SCAFFOLD),
                str(destination),
                "--name",
                name,
                *extra,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        for filename in ("node.py", "client.py", "pyproject.toml", "README.md"):
            assert (destination / filename).is_file()
        compile((destination / "node.py").read_text(), "node.py", "exec")
        compile((destination / "client.py").read_text(), "client.py", "exec")
        with (destination / "pyproject.toml").open("rb") as handle:
            pyproject = tomllib.load(handle)
        expected_project = f"easyremote-case-{name.replace('_', '-')}"
        assert pyproject["project"]["name"] == expected_project
        readme = (destination / "README.md").read_text(encoding="utf-8")
        for heading in (
            "## Concrete use case",
            "## Requirements",
            "## Existing approach",
            "## EasyRemote approach",
            "## Effect",
        ):
            assert heading in readme
