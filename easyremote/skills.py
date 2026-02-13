#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Skill-oriented helpers for low-boilerplate remote agent capability wiring.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, TypeVar, Union, cast

from .decorators import remote as remote_decorator

T = TypeVar("T", bound=Callable[..., Any])

_PIPELINE_SCHEMA = "easyremote.remote-skill-pipeline"
_PIPELINE_VERSION = "1.0"
_CAPABILITY_SPEC_ATTR = "__easyremote_remote_capability__"

# ---------------------------------------------------------------------------
# Minimal YAML frontmatter parser (no pyyaml dependency)
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?\n)---[ \t]*\n", re.DOTALL)


def _coerce_yaml_scalar(value: str) -> Any:
    """Convert a YAML scalar string to bool/int/float/None/str."""
    stripped = value.strip()
    if not stripped:
        return ""
    lower = stripped.lower()
    if lower in ("true", "yes", "on"):
        return True
    if lower in ("false", "no", "off"):
        return False
    if lower in ("null", "~"):
        return None
    # Try int
    if stripped.lstrip("-").isdigit():
        return int(stripped)
    # Try float
    try:
        return float(stripped)
    except ValueError:
        pass
    # Strip surrounding quotes
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in ('"', "'"):
        return stripped[1:-1]
    return stripped


def _parse_inline_list(value: str) -> List[Any]:
    """Parse ``[a, b, c]`` into a Python list of coerced scalars."""
    inner = value.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1]
    items: List[Any] = []
    for piece in inner.split(","):
        piece = piece.strip()
        if piece:
            items.append(_coerce_yaml_scalar(piece))
    return items


def _parse_yaml_frontmatter(text: str) -> Dict[str, Any]:
    """
    Extract ``---`` delimited frontmatter and parse a controlled YAML subset.

    Supports:
    - Flat ``key: value`` scalars
    - Inline lists ``[a, b, c]``
    - Up to 3 levels of indented mapping (2-space indent per level)
    - ``#`` comment lines
    - Colons inside values (split only on first ``: ``)
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return {}
    raw = match.group(1)
    root: Dict[str, Any] = {}
    # Stack of (indent_level, current_dict)
    stack: List[tuple[int, Dict[str, Any]]] = [(0, root)]

    for line in raw.splitlines():
        # Skip blank lines and comment lines
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Determine indent (number of leading spaces)
        indent = len(line) - len(line.lstrip(" "))

        # Pop stack until we find the right parent level
        while len(stack) > 1 and indent < stack[-1][0]:
            stack.pop()

        current = stack[-1][1]

        # Split key: value at first ": "
        colon_pos = stripped.find(": ")
        if colon_pos == -1:
            # Could be "key:" with no value (start of nested mapping)
            if stripped.endswith(":"):
                key = stripped[:-1].strip()
                nested: Dict[str, Any] = {}
                current[key] = nested
                stack.append((indent + 2, nested))
            continue

        key = stripped[:colon_pos].strip()
        value_str = stripped[colon_pos + 2:]

        if value_str.strip().startswith("["):
            current[key] = _parse_inline_list(value_str)
        else:
            current[key] = _coerce_yaml_scalar(value_str)

    return root


def _normalize_metadata(metadata: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if metadata is None:
        return {}
    return dict(metadata)


def _normalize_load_balancing(
    load_balancing: Union[bool, str, Mapping[str, Any]],
) -> Union[bool, str, Dict[str, Any]]:
    if isinstance(load_balancing, (bool, str)):
        return load_balancing
    if isinstance(load_balancing, Mapping):
        return dict(load_balancing)
    raise ValueError("load_balancing must be bool, str or mapping")


def _normalize_languages(languages: Optional[Iterable[Any]]) -> List[str]:
    if languages is None:
        return []

    normalized: List[str] = []
    for item in languages:
        value = str(item).strip()
        if not value:
            continue
        value = value.replace("_", "-").lower()
        normalized.append(value)
    return sorted(set(normalized))


def _non_empty(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("{0} cannot be empty".format(field_name))
    return normalized


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _parse_pipeline_payload(
    payload: Union[str, bytes, Mapping[str, Any]],
) -> Dict[str, Any]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")

    if isinstance(payload, str):
        parsed = json.loads(payload)
    elif isinstance(payload, Mapping):
        parsed = dict(payload)
    else:
        raise TypeError("pipeline payload must be dict, json str, or utf-8 bytes")

    if not isinstance(parsed, dict):
        raise ValueError("pipeline payload must decode to object")

    return parsed


@dataclass(frozen=True)
class MediaFrame:
    """
    Generic media frame for streaming payloads (audio/video/text/binary).
    """

    payload: Any
    media_type: str = "application/octet-stream"
    codec: Optional[str] = None
    sequence: Optional[int] = None
    timestamp_ms: Optional[int] = None
    end_of_stream: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


def stream_bytes(
    data: bytes,
    *,
    chunk_size: int = 4096,
    media_type: str = "application/octet-stream",
    codec: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Iterator[MediaFrame]:
    """
    Split bytes into MediaFrame chunks with end-of-stream marker on last frame.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")

    chunk_count = (len(data) + chunk_size - 1) // chunk_size
    chunk_count = max(chunk_count, 1)
    base_metadata = _normalize_metadata(metadata)

    for index in range(chunk_count):
        start = index * chunk_size
        end = start + chunk_size
        yield MediaFrame(
            payload=data[start:end],
            media_type=media_type,
            codec=codec,
            sequence=index,
            end_of_stream=index == chunk_count - 1,
            metadata=dict(base_metadata),
        )


def stream_audio_pcm(
    pcm_bytes: bytes,
    *,
    frame_bytes: int = 3200,
    sample_rate_hz: int = 16000,
    channels: int = 1,
    codec: str = "pcm16",
    metadata: Optional[Mapping[str, Any]] = None,
) -> Iterator[MediaFrame]:
    """
    Build audio media frames from PCM bytes for low-latency voice pipelines.
    """
    if sample_rate_hz < 1:
        raise ValueError("sample_rate_hz must be positive")
    if channels < 1:
        raise ValueError("channels must be positive")

    merged_metadata = _normalize_metadata(metadata)
    merged_metadata.setdefault("sample_rate_hz", sample_rate_hz)
    merged_metadata.setdefault("channels", channels)

    for frame in stream_bytes(
        pcm_bytes,
        chunk_size=frame_bytes,
        media_type="audio/raw",
        codec=codec,
        metadata=merged_metadata,
    ):
        yield frame


@dataclass
class CapabilitySpec:
    """
    Serializable capability descriptor used by pipeline transport.
    """

    alias: str
    function_name: str
    node_id: Optional[str] = None
    timeout: Optional[float] = None
    stream: bool = False
    load_balancing: Union[bool, str, Dict[str, Any]] = True
    media_type: str = "application/json"
    codec: Optional[str] = None
    languages: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    gateway_address: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alias": self.alias,
            "function_name": self.function_name,
            "node_id": self.node_id,
            "timeout": self.timeout,
            "stream": self.stream,
            "load_balancing": self.load_balancing,
            "media_type": self.media_type,
            "codec": self.codec,
            "languages": list(self.languages),
            "metadata": dict(self.metadata),
            "gateway_address": self.gateway_address,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CapabilitySpec":
        alias = _non_empty(payload.get("alias", ""), "alias")
        function_name = _non_empty(payload.get("function_name", ""), "function_name")
        media_type = _non_empty(payload.get("media_type", "application/json"), "media_type")
        metadata = _normalize_metadata(payload.get("metadata"))
        raw_languages = payload.get("languages")
        if raw_languages is None:
            raw_languages = metadata.get("languages")
        return cls(
            alias=alias,
            function_name=function_name,
            node_id=_optional_str(payload.get("node_id")),
            timeout=payload.get("timeout"),
            stream=bool(payload.get("stream", False)),
            load_balancing=_normalize_load_balancing(
                payload.get("load_balancing", True)
            ),
            media_type=media_type,
            codec=_optional_str(payload.get("codec")),
            languages=_normalize_languages(raw_languages),
            metadata=metadata,
            gateway_address=_optional_str(payload.get("gateway_address")),
        )


class RemotePipeline:
    """
    Callable pipeline facade for invoking remote capabilities by capability name.
    """

    def __init__(self, skill: "RemoteSkill") -> None:
        self._skill = skill

    def __call__(self, capability_name: str, *args: Any, **kwargs: Any) -> Any:
        return self._skill.call(capability_name, *args, **kwargs)

    def capabilities(self) -> list[str]:
        return self._skill.capability_names()

    def capability_specs(self) -> Dict[str, Dict[str, Any]]:
        return self._skill.capability_specs()


class RemoteSkill:
    """
    Minimal-config remote capability toolkit for agent skills.

    Typical flow:
    1. Register capabilities via decorators.
    2. Export pipeline JSON and transmit to another device.
    3. Rebuild callable pipeline from received JSON.
    """

    def __init__(
        self,
        *,
        name: str = "remote-skill",
        gateway_address: Optional[str] = None,
        namespace: str = "",
    ) -> None:
        self.name = _non_empty(name, "name")
        self.gateway_address = _optional_str(gateway_address)
        self.namespace = _optional_str(namespace) or ""
        self._capabilities: Dict[str, CapabilitySpec] = {}
        self._modules: Dict[str, Dict[str, Any]] = {}

    def _resolve_function_name(self, function_name: str) -> str:
        normalized = _non_empty(function_name, "function_name")
        if self.namespace and not normalized.startswith(self.namespace + "."):
            return "{0}.{1}".format(self.namespace, normalized)
        return normalized

    def _attach_proxy(
        self,
        spec: CapabilitySpec,
        template: Optional[Callable[..., Any]] = None,
    ) -> Callable[..., Any]:
        if template is None:
            def placeholder(*args: Any, **kwargs: Any) -> Any:
                return {"args": args, "kwargs": kwargs}

            placeholder.__name__ = spec.alias
            template = placeholder

        proxy = remote_decorator(
            function_name=spec.function_name,
            node_id=spec.node_id,
            timeout=spec.timeout,
            stream=spec.stream,
            load_balancing=spec.load_balancing,
            gateway_address=spec.gateway_address or self.gateway_address,
        )(template)
        if spec.languages and "languages" not in spec.metadata:
            spec.metadata["languages"] = list(spec.languages)
        setattr(proxy, _CAPABILITY_SPEC_ATTR, spec.to_dict())
        self._capabilities[spec.alias] = spec
        setattr(self, spec.alias, proxy)
        return proxy

    def attach_module(
        self,
        module_id: str,
        source: str,
        language: str = "python",
    ) -> None:
        """
        Attach a runtime code module that will be transferred with the pipeline.
        """
        mid = _non_empty(module_id, "module_id")
        src = source.strip() if isinstance(source, str) else ""
        if not src:
            raise ValueError("source cannot be empty")
        lang = str(language).strip().lower() or "python"
        sha256 = hashlib.sha256(src.encode("utf-8")).hexdigest()
        self._modules[mid] = {
            "module_id": mid,
            "language": lang,
            "source": src,
            "sha256": sha256,
        }

    def remote(
        self,
        func: Optional[Callable[..., Any]] = None,
        *,
        name: Optional[str] = None,
        function_name: Optional[str] = None,
        node_id: Optional[str] = None,
        timeout: Optional[float] = None,
        stream: bool = False,
        load_balancing: Union[bool, str, Mapping[str, Any]] = True,
        languages: Optional[Iterable[Any]] = None,
        media_type: str = "application/json",
        codec: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        code_export: Optional[str] = None,
    ) -> Union[Callable[[T], T], T]:
        """
        Register a remote capability with minimal configuration.
        """

        def decorator(target: T) -> T:
            alias = _non_empty(name or target.__name__, "capability name")
            remote_name = self._resolve_function_name(function_name or alias)
            normalized_languages = _normalize_languages(languages)
            normalized_metadata = _normalize_metadata(metadata)
            if normalized_languages:
                normalized_metadata["languages"] = list(normalized_languages)
            if code_export is not None:
                export_name = str(code_export).strip()
                if export_name and self._modules:
                    last_module_id = list(self._modules.keys())[-1]
                    normalized_metadata["code_binding"] = {
                        "module_id": last_module_id,
                        "export": export_name,
                    }
            spec = CapabilitySpec(
                alias=alias,
                function_name=remote_name,
                node_id=node_id,
                timeout=timeout,
                stream=stream,
                load_balancing=_normalize_load_balancing(load_balancing),
                languages=normalized_languages,
                media_type=_non_empty(media_type, "media_type"),
                codec=_optional_str(codec),
                metadata=normalized_metadata,
                gateway_address=self.gateway_address,
            )
            self._attach_proxy(spec, template=target)
            return cast(T, getattr(self, alias))

        if func is not None and callable(func):
            return decorator(cast(T, func))
        return decorator

    capability = remote

    def media(
        self,
        func: Optional[Callable[..., Any]] = None,
        *,
        media_type: str,
        name: Optional[str] = None,
        function_name: Optional[str] = None,
        node_id: Optional[str] = None,
        timeout: Optional[float] = None,
        stream: bool = True,
        load_balancing: Union[bool, str, Mapping[str, Any]] = True,
        languages: Optional[Iterable[Any]] = None,
        codec: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        code_export: Optional[str] = None,
    ) -> Union[Callable[[T], T], T]:
        """
        Capability decorator for media-oriented calls (video/audio/text streams).
        """
        return self.remote(
            func,
            name=name,
            function_name=function_name,
            node_id=node_id,
            timeout=timeout,
            stream=stream,
            load_balancing=load_balancing,
            languages=languages,
            media_type=media_type,
            codec=codec,
            metadata=metadata,
            code_export=code_export,
        )

    def voice(
        self,
        func: Optional[Callable[..., Any]] = None,
        *,
        name: Optional[str] = None,
        function_name: Optional[str] = None,
        node_id: Optional[str] = None,
        timeout: Optional[float] = None,
        load_balancing: Union[bool, str, Mapping[str, Any]] = True,
        codec: str = "pcm16",
        languages: Optional[Iterable[Any]] = None,
        sample_rate_hz: int = 16000,
        channels: int = 1,
        metadata: Optional[Mapping[str, Any]] = None,
        code_export: Optional[str] = None,
    ) -> Union[Callable[[T], T], T]:
        """
        Capability decorator for voice/audio streaming use cases.
        """
        merged_metadata = _normalize_metadata(metadata)
        merged_metadata.setdefault("sample_rate_hz", sample_rate_hz)
        merged_metadata.setdefault("channels", channels)
        return self.media(
            func,
            media_type="audio/raw",
            name=name,
            function_name=function_name,
            node_id=node_id,
            timeout=timeout,
            stream=True,
            load_balancing=load_balancing,
            languages=languages,
            codec=codec,
            metadata=merged_metadata,
            code_export=code_export,
        )

    def capability_names(self) -> list[str]:
        return sorted(self._capabilities.keys())

    def capability_specs(self) -> Dict[str, Dict[str, Any]]:
        return {
            alias: self._capabilities[alias].to_dict()
            for alias in self.capability_names()
        }

    def capability_languages(self, capability_name: str) -> List[str]:
        normalized = _non_empty(capability_name, "capability_name")
        spec = self._capabilities.get(normalized)
        if spec is None:
            raise KeyError(
                "Unknown capability '{0}'. Available: {1}".format(
                    normalized,
                    ", ".join(self.capability_names()) or "<none>",
                )
            )
        return list(spec.languages)

    def get(self, capability_name: str) -> Callable[..., Any]:
        normalized = _non_empty(capability_name, "capability_name")
        if normalized not in self._capabilities:
            raise KeyError(
                "Unknown capability '{0}'. Available: {1}".format(
                    normalized,
                    ", ".join(self.capability_names()) or "<none>",
                )
            )

        handler = getattr(self, normalized, None)
        if handler is None or not callable(handler):
            raise KeyError("Capability '{0}' is not callable".format(normalized))
        return cast(Callable[..., Any], handler)

    def call(self, capability_name: str, *args: Any, **kwargs: Any) -> Any:
        return self.get(capability_name)(*args, **kwargs)

    def build_pipeline_function(self) -> RemotePipeline:
        return RemotePipeline(self)

    def export_pipeline(
        self,
        *,
        include_gateway: bool = False,
        as_json: bool = True,
    ) -> Union[str, Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "schema": _PIPELINE_SCHEMA,
            "version": _PIPELINE_VERSION,
            "skill_name": self.name,
            "namespace": self.namespace,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "capabilities": [
                self._capabilities[name].to_dict() for name in self.capability_names()
            ],
        }
        if include_gateway and self.gateway_address:
            payload["gateway_address"] = self.gateway_address
        if self._modules:
            payload["runtime_modules"] = list(self._modules.values())

        if as_json:
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return payload

    @classmethod
    def from_pipeline(
        cls,
        payload: Union[str, bytes, Mapping[str, Any]],
        *,
        gateway_address: Optional[str] = None,
    ) -> "RemoteSkill":
        parsed = _parse_pipeline_payload(payload)

        schema = _non_empty(parsed.get("schema", ""), "schema")
        if schema != _PIPELINE_SCHEMA:
            raise ValueError(
                "Unsupported pipeline schema: {0}".format(schema)
            )

        _non_empty(parsed.get("version", ""), "version")

        pipeline_gateway = _optional_str(parsed.get("gateway_address"))
        resolved_gateway = _optional_str(gateway_address) or pipeline_gateway

        skill_name = _optional_str(parsed.get("skill_name")) or "remote-skill"
        namespace = _optional_str(parsed.get("namespace")) or ""
        skill = cls(
            name=skill_name,
            gateway_address=resolved_gateway,
            namespace=namespace,
        )

        runtime_modules = parsed.get("runtime_modules")
        if isinstance(runtime_modules, list):
            for mod in runtime_modules:
                if isinstance(mod, Mapping):
                    mid = str(mod.get("module_id", "")).strip()
                    if mid:
                        skill._modules[mid] = dict(mod)

        capabilities = parsed.get("capabilities", [])
        if not isinstance(capabilities, list):
            raise ValueError("capabilities must be a list")

        for item in capabilities:
            if not isinstance(item, Mapping):
                raise ValueError("capabilities entries must be objects")
            spec = CapabilitySpec.from_dict(item)
            if resolved_gateway is not None:
                spec.gateway_address = resolved_gateway
            skill._attach_proxy(spec)

        return skill

    @classmethod
    def from_directory(
        cls,
        path: Union[str, Path],
        *,
        gateway_address: Optional[str] = None,
    ) -> "RemoteSkill":
        """
        Build a RemoteSkill from a directory containing ``skill.md`` (with YAML
        frontmatter declaring capabilities) and optional runtime module files.
        """
        base = Path(path)
        skill_md = base / "skill.md"
        if not skill_md.is_file():
            raise FileNotFoundError(
                "skill.md not found in {0}".format(base)
            )

        frontmatter = _parse_yaml_frontmatter(skill_md.read_text(encoding="utf-8"))
        if not frontmatter:
            raise ValueError("skill.md contains no YAML frontmatter")

        skill_name = str(frontmatter.get("name", "remote-skill")).strip()
        namespace = str(frontmatter.get("namespace", "")).strip()
        fm_gateway = _optional_str(frontmatter.get("gateway_address"))
        resolved_gateway = _optional_str(gateway_address) or fm_gateway

        skill = cls(
            name=skill_name,
            gateway_address=resolved_gateway,
            namespace=namespace,
        )

        # Attach runtime module before capabilities (code_export depends on _modules)
        runtime_module = frontmatter.get("runtime_module")
        module_id = frontmatter.get("module_id")
        if runtime_module is not None:
            runtime_path = base / str(runtime_module)
            if not runtime_path.is_file():
                raise FileNotFoundError(
                    "runtime_module '{0}' not found in {1}".format(
                        runtime_module, base
                    )
                )
            source = runtime_path.read_text(encoding="utf-8")
            mid = str(module_id).strip() if module_id else str(runtime_module)
            skill.attach_module(mid, source)

        # Register capabilities from frontmatter
        capabilities = frontmatter.get("capabilities")
        if isinstance(capabilities, dict):
            for alias, cap_def in capabilities.items():
                if not isinstance(cap_def, dict):
                    continue
                cap_type = str(cap_def.get("type", "remote")).strip().lower()

                # Build common kwargs
                kwargs: Dict[str, Any] = {"name": alias}
                fn_name = cap_def.get("function_name")
                if fn_name is not None:
                    kwargs["function_name"] = str(fn_name)
                if "languages" in cap_def:
                    kwargs["languages"] = cap_def["languages"]
                if "code_export" in cap_def:
                    kwargs["code_export"] = str(cap_def["code_export"])
                if "node_id" in cap_def:
                    kwargs["node_id"] = str(cap_def["node_id"])
                if "timeout" in cap_def:
                    kwargs["timeout"] = float(cap_def["timeout"])
                if "load_balancing" in cap_def:
                    kwargs["load_balancing"] = cap_def["load_balancing"]
                if "metadata" in cap_def and isinstance(cap_def["metadata"], dict):
                    kwargs["metadata"] = cap_def["metadata"]

                # Placeholder function for the capability
                def _placeholder(*args: Any, **kw: Any) -> Any:
                    return {"args": args, "kwargs": kw}

                _placeholder.__name__ = alias

                if cap_type == "media":
                    kwargs["media_type"] = str(
                        cap_def.get("media_type", "application/octet-stream")
                    )
                    if "stream" in cap_def:
                        kwargs["stream"] = bool(cap_def["stream"])
                    if "codec" in cap_def:
                        kwargs["codec"] = str(cap_def["codec"])
                    skill.media(_placeholder, **kwargs)
                elif cap_type == "voice":
                    if "codec" in cap_def:
                        kwargs["codec"] = str(cap_def["codec"])
                    if "sample_rate_hz" in cap_def:
                        kwargs["sample_rate_hz"] = int(cap_def["sample_rate_hz"])
                    if "channels" in cap_def:
                        kwargs["channels"] = int(cap_def["channels"])
                    skill.voice(_placeholder, **kwargs)
                else:
                    # Default: remote
                    if "stream" in cap_def:
                        kwargs["stream"] = bool(cap_def["stream"])
                    if "media_type" in cap_def:
                        kwargs["media_type"] = str(cap_def["media_type"])
                    if "codec" in cap_def:
                        kwargs["codec"] = str(cap_def["codec"])
                    skill.remote(_placeholder, **kwargs)

        return skill


def pipeline_function(
    payload: Union[str, bytes, Mapping[str, Any]],
    *,
    gateway_address: Optional[str] = None,
) -> RemotePipeline:
    """
    Build a cross-device pipeline callable from exported capability payload.
    """
    skill = RemoteSkill.from_pipeline(payload, gateway_address=gateway_address)
    return skill.build_pipeline_function()


__all__ = [
    "MediaFrame",
    "stream_bytes",
    "stream_audio_pcm",
    "CapabilitySpec",
    "RemotePipeline",
    "RemoteSkill",
    "pipeline_function",
]
