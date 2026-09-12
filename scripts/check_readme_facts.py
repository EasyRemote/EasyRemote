#!/usr/bin/env python3
"""Check bilingual README facts derived from package metadata and public code."""

from __future__ import annotations

import argparse
import ast
import tomllib
from pathlib import Path


def sdk_requirement(pyproject: str) -> str:
    dependencies = tomllib.loads(pyproject)["project"]["dependencies"]
    matches = [item for item in dependencies if item.startswith("easynet-sdk")]
    if len(matches) != 1:
        raise ValueError("expected exactly one easynet-sdk requirement")
    return matches[0]


def context_methods(source: str) -> set[str]:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Context":
            return {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    raise ValueError("Context class is missing")


def errors(
    english: str,
    chinese: str,
    pyproject: str,
    context_source: str,
) -> list[str]:
    problems: list[str] = []
    requirement = sdk_requirement(pyproject)
    methods = context_methods(context_source)
    for name, readme in (("English", english), ("Chinese", chinese)):
        if requirement not in readme:
            problems.append(f"{name} README omits SDK requirement: {requirement}")
        for fact in ("binary_v1", "Local active", "advertisement"):
            if fact not in readme:
                problems.append(f"{name} README omits runtime fact: {fact}")
        for method in ("call", "invoke", "stream"):
            if method not in methods:
                problems.append(f"Context.{method} is documented but absent")
            if f"Context.{method}" not in readme:
                problems.append(f"{name} README omits implemented Context.{method}")
        if "SOURCE_RELEASE_SCOPE.md" not in readme:
            problems.append(f"{name} README omits public source scope")
    stale = (
        "globally callable capability",
        "There is no switch for this layer, no configuration",
        "这一层没有开关、没有配置",
        "获得全球可调用性",
        "pip install --pre --upgrade easyremote",
    )
    for claim in stale:
        present_in_english = claim.casefold() in english.casefold()
        present_in_chinese = claim.casefold() in chinese.casefold()
        if present_in_english or present_in_chinese:
            problems.append(f"README contains stale claim: {claim}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    english = (root / "README.md").read_text(encoding="utf-8")
    chinese = (root / "README_zh.md").read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    context_source = (root / "easyremote/context.py").read_text(encoding="utf-8")
    if args.self_test:
        mutated = english.replace("easynet-sdk>=0.162.9,<0.163", "SDK line")
        if not any(
            "English README omits SDK requirement" in item
            for item in errors(mutated, chinese, pyproject, context_source)
        ):
            raise SystemExit("self-test failed to detect dependency drift")
        print("README fact checker self-test passed")
        return 0
    problems = errors(english, chinese, pyproject, context_source)
    if problems:
        raise SystemExit("\n".join(problems))
    print("English and Chinese README facts match package metadata and Context")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
