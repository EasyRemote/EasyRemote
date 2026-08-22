#!/usr/bin/env python3
"""Synchronize committed EasyRemote version projections transactionally."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

VERSION_PATTERN = re.compile(
    r"[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?"
    r"(?:[.+-][0-9A-Za-z-]+)*"
)
VERSION_ASSIGNMENT = re.compile(
    r'(?m)^__version__ = "(?P<version>[^"]+)"$'
)


@dataclass(frozen=True)
class Projection:
    """One validated file replacement in a version synchronization."""

    path: Path
    original: bytes
    updated: bytes


def _replace_file(source: Path, target: Path) -> None:
    os.replace(source, target)


class ProjectVersionSynchronizer:
    """Own the finite set of package-version projections."""

    def __init__(
        self,
        root: Path,
        replace_file: Callable[[Path, Path], None] = _replace_file,
    ) -> None:
        self.root = root.resolve()
        self._replace_file = replace_file
        self.version_path = self.root / "easyremote" / "_version.py"
        self.policy_path = self.root / "easyremote" / "edge-adapter-policy.v1.json"

    def current_version(self) -> str:
        source = self.version_path.read_text(encoding="utf-8")
        match = VERSION_ASSIGNMENT.search(source)
        if match is None:
            raise ValueError(f"missing __version__ assignment: {self.version_path}")
        return match.group("version")

    def projections(self, version: str) -> tuple[Projection, ...]:
        self._validate_version(version)

        version_source = self.version_path.read_text(encoding="utf-8")
        updated_source, replacements = VERSION_ASSIGNMENT.subn(
            f'__version__ = "{version}"', version_source
        )
        if replacements != 1:
            raise ValueError(
                f"expected one __version__ assignment in {self.version_path}, "
                f"found {replacements}"
            )

        policy = json.loads(self.policy_path.read_text(encoding="utf-8"))
        package = policy.get("package")
        if not isinstance(package, dict) or package.get("name") != "easyremote":
            raise ValueError(f"invalid package projection: {self.policy_path}")
        if not isinstance(package.get("current_version"), str):
            raise ValueError(f"missing current_version projection: {self.policy_path}")
        package["current_version"] = version
        updated_policy = json.dumps(policy, indent=2, ensure_ascii=False) + "\n"

        return (
            Projection(
                self.version_path,
                self.version_path.read_bytes(),
                updated_source.encode(),
            ),
            Projection(
                self.policy_path,
                self.policy_path.read_bytes(),
                updated_policy.encode(),
            ),
        )

    def drift(self, version: str) -> tuple[Path, ...]:
        return tuple(
            item.path
            for item in self.projections(version)
            if item.original != item.updated
        )

    def synchronize(self, version: str) -> tuple[Path, ...]:
        changed = tuple(
            item for item in self.projections(version) if item.original != item.updated
        )
        if not changed:
            return ()

        staged: dict[Path, Path] = {}
        replaced: list[Projection] = []
        try:
            for item in changed:
                descriptor, temporary = tempfile.mkstemp(
                    prefix=f".{item.path.name}.", dir=item.path.parent
                )
                temporary_path = Path(temporary)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(item.updated)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary_path, item.path.stat().st_mode)
                staged[item.path] = temporary_path

            for item in changed:
                self._replace_file(staged.pop(item.path), item.path)
                replaced.append(item)
        except BaseException:
            for item in reversed(replaced):
                item.path.write_bytes(item.original)
            raise
        finally:
            for temporary_path in staged.values():
                temporary_path.unlink(missing_ok=True)

        return tuple(item.path for item in changed)

    @staticmethod
    def _validate_version(version: str) -> None:
        if VERSION_PATTERN.fullmatch(version) is None:
            raise ValueError(f"invalid Tide/PEP 440 version: {version!r}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize EasyRemote package-version projections."
    )
    parser.add_argument("version", help="explicit version resolved once by Tide")
    parser.add_argument(
        "--check", action="store_true", help="report drift without writing files"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    synchronizer = ProjectVersionSynchronizer(args.root)
    try:
        drift = synchronizer.drift(args.version)
        if args.check:
            if drift:
                for path in drift:
                    print(f"version projection mismatch: {path}")
                return 1
            print(f"EasyRemote version projections match {args.version}")
            return 0

        changed = synchronizer.synchronize(args.version)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    for path in changed:
        print(f"updated {path.relative_to(synchronizer.root)}")
    if not changed:
        print(f"EasyRemote version projections already match {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
