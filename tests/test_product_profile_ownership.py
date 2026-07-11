"""Product profile ownership gates for EasyRemote production modules."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "easyremote"
FORBIDDEN_SDK_NAMES = {
    "AgentLifecycleAdapter",
    "DaemonProfileBridge",
}
FORBIDDEN_SDK_MODULES = {
    "easynet_sdk.admin",
    "easynet_sdk.mission",
    "easynet_sdk.profile_bridge",
    "easynet_sdk.system_abilities",
}
FORBIDDEN_SDK_SUBMODULES = {
    module.rsplit(".", 1)[-1] for module in FORBIDDEN_SDK_MODULES
}


def test_product_profiles_do_not_import_sdk_product_models() -> None:
    violations: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.name == "easynet_sdk"
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_SDK_MODULES:
                        violations.append(
                            f"{path.relative_to(ROOT)} imports {alias.name}"
                        )
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module in FORBIDDEN_SDK_MODULES:
                    violations.append(f"{path.relative_to(ROOT)} imports {module}")
                if module == "easynet_sdk":
                    for alias in node.names:
                        if (
                            alias.name in FORBIDDEN_SDK_SUBMODULES
                            or _forbidden_sdk_name(alias.name)
                        ):
                            violations.append(
                                f"{path.relative_to(ROOT)} imports"
                                f" easynet_sdk.{alias.name}"
                            )
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in aliases
                and _forbidden_sdk_name(node.attr)
            ):
                violations.append(
                    f"{path.relative_to(ROOT)} references easynet_sdk.{node.attr}"
                )
    assert not violations, "\n".join(violations)


def test_retired_mixed_profile_bridge_is_absent() -> None:
    assert not (PACKAGE / "_sdk_profiles.py").exists()
    imports = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "_sdk_profiles":
                imports.append(str(path.relative_to(ROOT)))
    assert imports == []


def test_product_ability_names_have_one_owner() -> None:
    owners: dict[str, list[str]] = {
        ability: []
        for ability in (
            "mission.run",
            "mission.track",
            "mission.cancel",
            "mission.events",
            "agent.start",
            "agent.list",
            "agent.stop",
            "agent.refresh",
        )
    }
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in owners
            ):
                owners[node.value].append(str(path.relative_to(ROOT)))
    assert owners == {
        ability: ["easyremote/_product_abilities.py"] for ability in owners
    }


def _forbidden_sdk_name(name: str) -> bool:
    return (
        name in FORBIDDEN_SDK_NAMES
        or name.startswith("Mission")
        or name.endswith("SystemAbility")
    )
