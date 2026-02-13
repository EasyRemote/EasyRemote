#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Guardrails for decorator-route proxy function implementations.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

import ast
from pathlib import Path


def _is_remote_decorator(decorator: ast.expr) -> bool:
    if isinstance(decorator, ast.Name):
        return decorator.id == "remote"
    if isinstance(decorator, ast.Call):
        target = decorator.func
        if isinstance(target, ast.Name):
            return target.id == "remote"
        if isinstance(target, ast.Attribute):
            return target.attr == "remote"
    if isinstance(decorator, ast.Attribute):
        return decorator.attr == "remote"
    return False


def _is_register_decorator(decorator: ast.expr) -> bool:
    if isinstance(decorator, ast.Name):
        return decorator.id == "register"
    if isinstance(decorator, ast.Call):
        target = decorator.func
        if isinstance(target, ast.Name):
            return target.id == "register"
        if isinstance(target, ast.Attribute):
            return target.attr == "register"
    if isinstance(decorator, ast.Attribute):
        return decorator.attr == "register"
    return False


def _has_pass_only_body(function_node: ast.AST) -> bool:
    if not isinstance(function_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    if len(function_node.body) != 1:
        return False
    return isinstance(function_node.body[0], ast.Pass)


def test_remote_and_register_decorated_functions_are_not_pass_only_placeholders() -> None:
    project_root = Path(__file__).resolve().parents[1]
    target_files = [
        path
        for path in project_root.rglob("*.py")
        if "__pycache__" not in path.parts
        and ".venv" not in path.parts
        and ".git" not in path.parts
        and "easyremote/core/protos" not in str(path)
    ]

    violations: list[str] = []
    for file_path in target_files:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not any(
                _is_remote_decorator(decorator) or _is_register_decorator(decorator)
                for decorator in node.decorator_list
            ):
                continue
            if _has_pass_only_body(node):
                violations.append(f"{file_path}:{node.name}")

    assert not violations, (
        "Remote/register decorated functions must not use pass-only placeholder bodies: "
        + ", ".join(violations)
    )
