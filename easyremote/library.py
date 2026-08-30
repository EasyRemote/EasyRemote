"""Install network-native library contracts as local Python modules.

The library projection is deliberately local and deterministic. Importing a
generated module never performs discovery or network I/O; only calling one of
its ``@remote`` stubs enters the EasyNet invocation path.
"""

from __future__ import annotations

import json
import keyword
import os
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import easynet_sdk

from .errors import InvalidArgument

__all__ = [
    "LIBRARY_FORMAT",
    "InstalledLibrary",
    "LibraryExport",
    "LibraryManifest",
    "activate_library_root",
    "install_library",
    "library_root",
    "list_libraries",
    "remove_library",
]

LIBRARY_FORMAT = "easyremote.library/v1"
LIBRARY_ROOT_ENV = "EASYREMOTE_LIBRARY_ROOT"
LOCK_FILENAME = "easyremote-library.lock.json"
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_REALM = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")


def _invalid(message: str, reason: str) -> InvalidArgument:
    return InvalidArgument(message, reason=reason)


def _identifier(value: object, *, field: str) -> str:
    candidate = str(value or "").strip()
    if not candidate.isidentifier() or keyword.iskeyword(candidate):
        raise _invalid(
            f"{field} must be a valid Python identifier, got {candidate!r}",
            "invalid_library_identifier",
        )
    return candidate


def _mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _invalid(f"{field} must be a JSON object", "invalid_library_manifest")
    return {str(key): item for key, item in value.items()}


@dataclass(frozen=True)
class LibraryExport:
    """One typed Python symbol bound to one remote ability contract."""

    python_name: str
    ability: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    description: str = ""
    descriptor_ref: str = ""
    owner_ura: str = ""
    call_mode: str = "rpc"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> LibraryExport:
        python_name = _identifier(raw.get("python_name"), field="python_name")
        ability = str(raw.get("ability") or "").strip()
        if not ability:
            raise _invalid(
                f"export {python_name!r} must name an ability",
                "missing_library_ability",
            )
        call_mode = str(raw.get("call_mode") or "rpc").strip()
        if call_mode != "rpc":
            raise _invalid(
                f"export {python_name!r} must use call_mode 'rpc'; streaming and"
                " bidi library projections are not defined in v1",
                "invalid_library_call_mode",
            )
        descriptor_ref = str(raw.get("descriptor_ref") or "").strip()
        if descriptor_ref:
            try:
                descriptor = easynet_sdk.project_descriptor_ref(descriptor_ref)
            except easynet_sdk.SDKError as exc:
                raise _invalid(
                    f"export {python_name!r} has invalid descriptor_ref: {exc}",
                    "invalid_library_descriptor_ref",
                ) from exc
            if descriptor.action != "invoke":
                raise _invalid(
                    f"export {python_name!r} descriptor action must be 'invoke'",
                    "library_descriptor_action_mismatch",
                )
            try:
                ability_projection = easynet_sdk.parse_ura(ability)
            except easynet_sdk.SDKError:
                descriptor_matches = descriptor.public_name == ability
            else:
                descriptor_matches = (
                    ability_projection.kind == "ability"
                    and descriptor.ability_ura == ability_projection.ura
                )
            if not descriptor_matches:
                raise _invalid(
                    f"export {python_name!r} descriptor_ref does not bind ability"
                    f" {ability!r}",
                    "library_descriptor_ability_mismatch",
                )
            descriptor_ref = descriptor.descriptor_ref
        return cls(
            python_name=python_name,
            ability=ability,
            input_schema=_mapping(raw.get("input_schema"), field="input_schema"),
            output_schema=_mapping(raw.get("output_schema"), field="output_schema"),
            description=str(raw.get("description") or "").strip(),
            descriptor_ref=descriptor_ref,
            owner_ura=str(raw.get("owner_ura") or "").strip(),
            call_mode=call_mode,
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "python_name": self.python_name,
            "ability": self.ability,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "description": self.description,
            "descriptor_ref": self.descriptor_ref,
            "owner_ura": self.owner_ura,
            "call_mode": self.call_mode,
        }


@dataclass(frozen=True)
class LibraryManifest:
    """A versioned interface package; provider implementation is never included."""

    realm: str
    publisher: str
    package: str
    version: str
    exports: tuple[LibraryExport, ...]
    format: str = LIBRARY_FORMAT

    @property
    def coordinate(self) -> str:
        return f"@{self.publisher}/{self.package}@{self.version}"

    @property
    def default_import(self) -> str:
        return f"easyremote.{self.publisher}.{self.package}"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> LibraryManifest:
        manifest_format = str(raw.get("format") or "").strip()
        if manifest_format != LIBRARY_FORMAT:
            raise _invalid(
                f"manifest format must be {LIBRARY_FORMAT!r}",
                "unsupported_library_format",
            )
        realm = str(raw.get("realm") or "").strip()
        if not _REALM.fullmatch(realm):
            raise _invalid(
                f"realm must be a DNS-like name, got {realm!r}",
                "invalid_library_realm",
            )
        publisher = _identifier(raw.get("publisher"), field="publisher")
        package = _identifier(raw.get("package"), field="package")
        version = str(raw.get("version") or "").strip()
        if not _SEMVER.fullmatch(version):
            raise _invalid(
                f"version must be an exact semantic version, got {version!r}",
                "invalid_library_version",
            )
        exports_raw = raw.get("exports")
        if not isinstance(exports_raw, Sequence) or isinstance(
            exports_raw, (str, bytes)
        ):
            raise _invalid("exports must be a JSON array", "invalid_library_manifest")
        exports = tuple(
            LibraryExport.from_mapping(_mapping(item, field="export"))
            for item in exports_raw
        )
        if not exports:
            raise _invalid(
                "a library must export at least one function", "empty_library_exports"
            )
        names = [item.python_name for item in exports]
        if len(names) != len(set(names)):
            raise _invalid(
                "library export names must be unique", "duplicate_library_export"
            )
        return cls(
            format=manifest_format,
            realm=realm,
            publisher=publisher,
            package=package,
            version=version,
            exports=exports,
        )

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> LibraryManifest:
        source = Path(path)
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise _invalid(
                f"cannot read library manifest {source}: {exc}",
                "invalid_library_manifest",
            ) from exc
        return cls.from_mapping(_mapping(raw, field="manifest"))

    def to_mapping(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "realm": self.realm,
            "publisher": self.publisher,
            "package": self.package,
            "version": self.version,
            "exports": [item.to_mapping() for item in self.exports],
        }


@dataclass(frozen=True)
class InstalledLibrary:
    """One locally materialized library facade."""

    coordinate: str
    realm: str
    import_name: str
    version: str
    path: Path


def library_root(root: str | os.PathLike[str] | None = None) -> Path:
    """Return the configured interface projection root."""
    if root is not None:
        return Path(root).expanduser().resolve()
    configured = os.environ.get(LIBRARY_ROOT_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".easyremote" / "libraries").resolve()


def activate_library_root(root: str | os.PathLike[str] | None = None) -> Path:
    """Attach one local projection root to the already imported package."""
    projection = library_root(root) / "easyremote"
    if projection.is_dir():
        import easyremote

        location = str(projection)
        if location not in easyremote.__path__:
            easyremote.__path__.insert(0, location)
    return projection


def install_library(
    manifest_path: str | os.PathLike[str],
    *,
    root: str | os.PathLike[str] | None = None,
    alias: str | None = None,
) -> InstalledLibrary:
    """Materialize a manifest as an importable, typed Python facade."""
    manifest = LibraryManifest.load(manifest_path)
    segments = (
        (_identifier(alias, field="alias"),)
        if alias is not None
        else (manifest.publisher, manifest.package)
    )
    _reject_core_collision(segments[0])
    projection_root = library_root(root)
    package_dir = projection_root / "easyremote" / Path(*segments)
    lock_path = package_dir / LOCK_FILENAME
    if lock_path.is_file():
        current = _read_lock(lock_path)
        expected = (manifest.realm, manifest.publisher, manifest.package)
        actual = (
            str(current.get("realm") or ""),
            str(current.get("publisher") or ""),
            str(current.get("package") or ""),
        )
        if actual != expected:
            raise _invalid(
                f"import {'.'.join(('easyremote', *segments))!r} is already owned"
                " by another library",
                "library_import_collision",
            )

    source = _render_module(manifest)
    stub = _render_stub(manifest)
    compile(source, str(package_dir / "__init__.py"), "exec")
    compile(stub, str(package_dir / "__init__.pyi"), "exec")
    package_dir.mkdir(parents=True, exist_ok=True)
    import_name = ".".join(("easyremote", *segments))
    lock = {
        **manifest.to_mapping(),
        "coordinate": manifest.coordinate,
        "import_name": import_name,
    }
    _atomic_write(package_dir / "__init__.py", source)
    _atomic_write(package_dir / "__init__.pyi", stub)
    _atomic_write(package_dir / "py.typed", "\n")
    _atomic_write(
        lock_path,
        json.dumps(lock, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    activate_library_root(projection_root)
    return InstalledLibrary(
        coordinate=manifest.coordinate,
        realm=manifest.realm,
        import_name=import_name,
        version=manifest.version,
        path=package_dir,
    )


def list_libraries(
    *, root: str | os.PathLike[str] | None = None
) -> tuple[InstalledLibrary, ...]:
    """List installed interface projections from lock files."""
    projection_root = library_root(root)
    package_root = projection_root / "easyremote"
    if not package_root.is_dir():
        return ()
    installed: list[InstalledLibrary] = []
    for lock_path in sorted(package_root.rglob(LOCK_FILENAME)):
        raw = _read_lock(lock_path)
        installed.append(
            InstalledLibrary(
                coordinate=str(raw.get("coordinate") or ""),
                realm=str(raw.get("realm") or ""),
                import_name=str(raw.get("import_name") or ""),
                version=str(raw.get("version") or ""),
                path=lock_path.parent,
            )
        )
    return tuple(installed)


def remove_library(
    import_name: str, *, root: str | os.PathLike[str] | None = None
) -> InstalledLibrary:
    """Remove one exact installed projection selected by import name."""
    match = next(
        (item for item in list_libraries(root=root) if item.import_name == import_name),
        None,
    )
    if match is None:
        raise _invalid(
            f"library import {import_name!r} is not installed",
            "library_not_installed",
        )
    shutil.rmtree(match.path)
    return match


def _reject_core_collision(segment: str) -> None:
    package_dir = Path(__file__).parent
    if (package_dir / f"{segment}.py").exists() or (package_dir / segment).exists():
        raise _invalid(
            f"library top-level module {segment!r} collides with EasyRemote",
            "library_import_collision",
        )


def _read_lock(path: Path) -> dict[str, Any]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), field="lock")
    except (OSError, json.JSONDecodeError) as exc:
        raise _invalid(
            f"cannot read installed library lock {path}: {exc}",
            "invalid_library_lock",
        ) from exc


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


_MISSING = object()


def _parameter_specs(export: LibraryExport) -> list[tuple[str, str, object]]:
    schema = export.input_schema
    if schema.get("type") != "object":
        raise _invalid(
            f"export {export.python_name!r} input_schema must have type 'object'",
            "unsupported_library_schema",
        )
    properties = _mapping(schema.get("properties", {}), field="properties")
    order_value = schema.get("x-easyremote-parameter-order", list(properties))
    if not isinstance(order_value, list) or set(order_value) != set(properties):
        raise _invalid(
            f"export {export.python_name!r} parameter order must name every property",
            "invalid_library_parameter_order",
        )
    order = [_identifier(name, field="parameter") for name in order_value]
    required_value = schema.get("required", [])
    if not isinstance(required_value, list) or not set(required_value) <= set(
        properties
    ):
        raise _invalid(
            f"export {export.python_name!r} required must name known properties",
            "invalid_library_required_parameters",
        )
    required = set(required_value)
    seen_optional = False
    result: list[tuple[str, str, object]] = []
    for name in order:
        property_schema = _mapping(properties[name], field=f"property {name}")
        annotation = _annotation(property_schema)
        if name in required:
            if seen_optional:
                raise _invalid(
                    f"export {export.python_name!r} places required parameter {name!r}"
                    " after an optional parameter",
                    "invalid_library_parameter_order",
                )
            default: object = _MISSING
        else:
            seen_optional = True
            default = property_schema.get("default", None)
            if default is None and "None" not in annotation:
                annotation = f"{annotation} | None"
        result.append((name, annotation, default))
    return result


def _annotation(schema: Mapping[str, Any]) -> str:
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        parts = [
            "None" if item == "null" else _annotation({**schema, "type": item})
            for item in schema_type
        ]
        return " | ".join(dict.fromkeys(parts))
    if schema_type == "string":
        return "str"
    if schema_type == "integer":
        return "int"
    if schema_type == "number":
        return "float"
    if schema_type == "boolean":
        return "bool"
    if schema_type == "array":
        items = schema.get("items")
        item_annotation = _annotation(items) if isinstance(items, Mapping) else "Any"
        return f"list[{item_annotation}]"
    if schema_type == "object":
        additional = schema.get("additionalProperties")
        value_annotation = (
            _annotation(additional) if isinstance(additional, Mapping) else "Any"
        )
        return f"dict[str, {value_annotation}]"
    return "Any"


def _signature(export: LibraryExport) -> str:
    parameters: list[str] = []
    for name, annotation, default in _parameter_specs(export):
        rendered = f"{name}: {annotation}"
        if default is not _MISSING:
            rendered += f" = {default!r}"
        parameters.append(rendered)
    return f"({', '.join(parameters)}) -> {_annotation(export.output_schema)}"


def _render_module(manifest: LibraryManifest) -> str:
    names = [item.python_name for item in manifest.exports]
    lines = [
        '"""Generated EasyRemote interface facade. Do not edit."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
        "from easyremote import FreshRoot, ResolvedTargetSubject, remote",
        "",
        f"__all__ = {names!r}",
        f"__easyremote_coordinate__ = {manifest.coordinate!r}",
        f"__easyremote_realm__ = {manifest.realm!r}",
        f"__version__ = {manifest.version!r}",
        "",
    ]
    for export in manifest.exports:
        options = [
            f"name={export.ability!r}",
            "invocation_policy=FreshRoot(ResolvedTargetSubject())",
        ]
        if export.descriptor_ref:
            options.append(f"descriptor_ref={export.descriptor_ref!r}")
        if export.owner_ura:
            options.append(f"owner_ura={export.owner_ura!r}")
        docstring = export.description or "Remote library function."
        lines.extend(
            [
                f"@remote({', '.join(options)})",
                f"def {export.python_name}{_signature(export)}:",
                f"    {docstring!r}",
                "    raise RuntimeError("
                "'EasyRemote remote stubs never execute locally')",
                "",
            ]
        )
    return "\n".join(lines)


def _render_stub(manifest: LibraryManifest) -> str:
    lines = [
        "from typing import Any",
        "",
        "__easyremote_coordinate__: str",
        "__easyremote_realm__: str",
        "__version__: str",
        "",
    ]
    for export in manifest.exports:
        lines.extend([f"def {export.python_name}{_signature(export)}: ...", ""])
    return "\n".join(lines)
