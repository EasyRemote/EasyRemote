#!/usr/bin/env python3
"""Create a minimal standalone EasyRemote provider/caller uv project."""

from __future__ import annotations

import argparse
import os
import re
import textwrap
from pathlib import Path

FUNCTION_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--name", default="process_value")
    parser.add_argument("--namespace", default="er")
    parser.add_argument("--stream", action="store_true")
    parser.add_argument(
        "--workspace-sources",
        action="store_true",
        help="resolve EasyRemote and easynet-sdk from this workspace",
    )
    args = parser.parse_args()

    if not FUNCTION_NAME.fullmatch(args.name):
        parser.error("--name must be a valid Python identifier")
    if not args.namespace.strip() or any(char.isspace() for char in args.namespace):
        parser.error("--namespace must be non-empty and contain no whitespace")

    destination = args.destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        parser.error(f"destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    values = {
        "__FUNCTION__": args.name,
        "__NAMESPACE__": args.namespace,
        "__PROJECT__": f"easyremote-case-{args.name.replace('_', '-')}",
    }
    templates = _stream_templates() if args.stream else _unary_templates()
    templates["pyproject.toml"] = _pyproject(destination, args.workspace_sources)
    for filename, template in templates.items():
        rendered = textwrap.dedent(template).lstrip()
        for marker, value in values.items():
            rendered = rendered.replace(marker, value)
        (destination / filename).write_text(rendered, encoding="utf-8")

    print(f"created {destination}")
    print("next: uv lock && uv run ruff check node.py client.py")
    return 0


def _pyproject(destination: Path, workspace_sources: bool) -> str:
    dependencies = '    "easyremote",\n'
    sources = ""
    if workspace_sources:
        repository = Path(__file__).resolve().parents[3]
        sdk = repository.parent / "EasyNet-Cli" / "sdk" / "python"
        easyremote_path = Path(os.path.relpath(repository, destination)).as_posix()
        sdk_path = Path(os.path.relpath(sdk, destination)).as_posix()
        dependencies += '    "easynet-sdk>=0.162.9,<0.163",\n'
        sources = (
            "\n[tool.uv.sources]\n"
            f'easyremote = {{ path = "{easyremote_path}", editable = true }}\n'
            f'easynet-sdk = {{ path = "{sdk_path}", editable = true }}\n'
        )
    return f'''
[project]
name = "__PROJECT__"
version = "0.1.0"
description = "A standalone bounded EasyRemote capability"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
{dependencies}]
{sources}
[dependency-groups]
dev = ["ruff>=0.13"]

[tool.ruff]
line-length = 88
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]
'''


def _unary_templates() -> dict[str, str]:
    return {
        "node.py": '''
            """Publish one bounded task."""

            from easyremote import ComputeNode

            node = ComputeNode(namespace="__NAMESPACE__")


            @node.register(description="Process one validated value.")
            def __FUNCTION__(value: int) -> dict[str, int]:
                if not 0 <= value <= 10_000:
                    raise ValueError("value must be between 0 and 10,000")
                return {"input": value, "result": value * 2}


            if __name__ == "__main__":
                node.serve()
        ''',
        "client.py": '''
            """Call the bounded task through a typed stub."""

            from pprint import pprint

            from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

            client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))


            @remote(client=client)
            def __FUNCTION__(value: int) -> dict[str, int]: ...


            if __name__ == "__main__":
                pprint(__FUNCTION__(value=21))
        ''',
        "README.md": _readme("one validated result", "Unary"),
    }


def _stream_templates() -> dict[str, str]:
    return {
        "node.py": '''
            """Publish one bounded finite stream."""

            from collections.abc import Iterator

            from easyremote import ComputeNode

            node = ComputeNode(namespace="__NAMESPACE__")


            @node.register(description="Stream a finite ordered sequence.")
            def __FUNCTION__(samples: int = 3) -> Iterator[dict[str, int]]:
                if not 1 <= samples <= 10:
                    raise ValueError("samples must be between 1 and 10")
                for sequence in range(1, samples + 1):
                    yield {"sequence": sequence, "value": sequence * 2}


            if __name__ == "__main__":
                node.serve()
        ''',
        "client.py": '''
            """Consume the finite stream through a typed stub."""

            from collections.abc import Iterator

            from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

            client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))


            @remote(client=client)
            def __FUNCTION__(samples: int = 3) -> Iterator[dict[str, int]]: ...


            if __name__ == "__main__":
                for item in __FUNCTION__.stream(samples=3):
                    print(item)
        ''',
        "README.md": _readme("a finite ordered sequence", "Server stream"),
    }


def _readme(task: str, carrier: str) -> str:
    return f'''
        # Bounded Remote Task

        ## Concrete use case

        A caller needs {task} from code that must remain on the provider machine.

        ## Requirements

        - Accept only typed, explicitly bounded inputs.
        - Keep implementation state and credentials provider-local.
        - Terminate deterministically and return a structured result.
        - Use the {carrier.lower()} carrier without exposing machine access.

        ## Existing approach

        A dedicated HTTP service adds deployment, authentication, routing, and
        operational ownership before this small task can be shared.

        ## EasyRemote approach

        The provider publishes one function with `@node.register`; the caller
        declares the same contract with `@remote`. EasyNet owns identity,
        authority, signing, routing, and receipts.

        ## Effect

        The function becomes a governed capability without turning the provider
        machine into a general remote-execution endpoint.

        ## Run

        ```bash
        uv sync
        uv run python node.py
        uv run python client.py
        ```
    '''


if __name__ == "__main__":
    raise SystemExit(main())
