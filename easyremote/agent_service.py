#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
User-facing remote agent service with installable skill pipelines.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union

from .skills import RemoteSkill


def _normalize_language(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized.replace("_", "-").lower()


def _normalize_languages(values: Optional[Iterable[str]]) -> List[str]:
    if values is None:
        return []
    normalized: List[str] = []
    for value in values:
        item = _normalize_language(value)
        if item:
            normalized.append(item)
    return sorted(set(normalized))


def _base_language(value: str) -> str:
    return value.split("-", 1)[0]


def _is_language_match(candidate: str, supported: str) -> bool:
    if candidate == supported:
        return True
    return _base_language(candidate) == _base_language(supported)


def _capability_supported_languages(spec: Mapping[str, Any]) -> List[str]:
    raw_languages = spec.get("languages")
    if raw_languages is None:
        metadata = spec.get("metadata")
        if isinstance(metadata, Mapping):
            raw_languages = metadata.get("languages")
    if raw_languages is None:
        return []
    if isinstance(raw_languages, str):
        return _normalize_languages([raw_languages])
    if isinstance(raw_languages, Sequence):
        return _normalize_languages(raw_languages)
    return []


@dataclass
class UserAgentProfile:
    """
    Per-user preferences for one remote agent service instance.
    """

    user_id: str
    preferred_language: str = "en-us"
    fallback_languages: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        user = str(self.user_id).strip()
        if not user:
            raise ValueError("user_id cannot be empty")
        self.user_id = user

        preferred = _normalize_language(self.preferred_language)
        if preferred is None:
            raise ValueError("preferred_language cannot be empty")
        self.preferred_language = preferred

        normalized_fallbacks = _normalize_languages(self.fallback_languages)
        self.fallback_languages = [
            item for item in normalized_fallbacks if item != self.preferred_language
        ]

    def language_priority(self, preferred_override: Optional[str] = None) -> List[str]:
        override = _normalize_language(preferred_override)
        if override:
            return [override]
        return [self.preferred_language, *self.fallback_languages]


@dataclass
class InstalledSkill:
    """
    Installed skill metadata for user-side runtime management.
    """

    name: str
    source: str
    installed_at: str
    skill: RemoteSkill
    metadata: Dict[str, Any] = field(default_factory=dict)


class RemoteAgentService:
    """
    User-facing remote agent service with dynamic skill installation.

    This service lets a user's software install remote skill payloads at runtime
    and execute capabilities immediately without process restart.
    """

    def __init__(
        self,
        *,
        user_id: str,
        preferred_language: str = "en-US",
        fallback_languages: Optional[Iterable[str]] = None,
        gateway_address: Optional[str] = None,
    ) -> None:
        self.profile = UserAgentProfile(
            user_id=user_id,
            preferred_language=preferred_language,
            fallback_languages=list(fallback_languages or []),
        )
        self.gateway_address = gateway_address
        self._installed_skills: Dict[str, InstalledSkill] = {}

    def _resolve_client(self, gateway_address: Optional[str] = None):
        from .core.nodes.client import Client, get_default_client

        existing = get_default_client()
        if existing is not None:
            return existing

        resolved_gateway = gateway_address or self.gateway_address
        if not resolved_gateway:
            raise ValueError(
                "gateway_address is required for node-targeted execution "
                "when no default client is configured"
            )
        return Client(resolved_gateway)

    def resolve_target_node_id(
        self,
        *,
        node_id: Optional[str] = None,
        user_id: Optional[str] = None,
        required_functions: Optional[Iterable[str]] = None,
        gateway_address: Optional[str] = None,
    ) -> str:
        """
        Resolve concrete remote node id by explicit node_id or user capability tag.
        """
        if node_id is not None:
            normalized = str(node_id).strip()
            if normalized:
                return normalized

        target_user = str(user_id or self.profile.user_id).strip()
        if not target_user:
            raise ValueError("user_id cannot be empty")

        client = self._resolve_client(gateway_address=gateway_address)
        matches = client.find_nodes(
            required_capabilities=[f"user:{target_user}"],
            required_functions=list(required_functions or []),
        )
        if not matches:
            raise KeyError(
                "No node found for user '{0}'. Expected capability tag "
                "'user:{0}' on target node.".format(target_user)
            )

        # Pressure-aware policy: choose the least loaded node for this user.
        matches.sort(
            key=lambda item: (
                float(item.get("current_load", 1.0)),
                str(item.get("node_id", "")),
            )
        )
        return str(matches[0]["node_id"])

    def _run_spec_on_node(
        self,
        spec: Mapping[str, Any],
        node_id: str,
        *args: Any,
        gateway_address: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        client = self._resolve_client(gateway_address=gateway_address)
        function_name = str(spec["function_name"]).strip()
        if not function_name:
            raise ValueError("function_name cannot be empty")

        if bool(spec.get("stream", False)):
            return client.stream_on_node(node_id, function_name, *args, **kwargs)
        return client.execute_on_node(node_id, function_name, *args, **kwargs)

    def set_language_preferences(
        self,
        *,
        preferred_language: str,
        fallback_languages: Optional[Iterable[str]] = None,
    ) -> None:
        self.profile = UserAgentProfile(
            user_id=self.profile.user_id,
            preferred_language=preferred_language,
            fallback_languages=list(fallback_languages or []),
            metadata=dict(self.profile.metadata),
        )

    def install_skill(
        self,
        payload: Union[str, bytes, Mapping[str, Any]],
        *,
        skill_name: Optional[str] = None,
        gateway_address: Optional[str] = None,
        source: str = "remote",
        metadata: Optional[Mapping[str, Any]] = None,
        replace: bool = True,
    ) -> str:
        """
        Install one remote skill payload for current user.
        """
        resolved_gateway = gateway_address or self.gateway_address
        skill = RemoteSkill.from_pipeline(payload, gateway_address=resolved_gateway)
        target_name = (skill_name or skill.name).strip()
        if not target_name:
            raise ValueError("skill_name cannot be empty")

        if not replace and target_name in self._installed_skills:
            raise ValueError("Skill '{0}' already installed".format(target_name))

        record = InstalledSkill(
            name=target_name,
            source=str(source).strip() or "remote",
            installed_at=datetime.now(timezone.utc).isoformat(),
            skill=skill,
            metadata=dict(metadata or {}),
        )
        self._installed_skills[target_name] = record
        return target_name

    def uninstall_skill(self, skill_name: str) -> bool:
        return self._installed_skills.pop(skill_name, None) is not None

    def get_skill(self, skill_name: str) -> RemoteSkill:
        record = self._installed_skills.get(skill_name)
        if record is None:
            raise KeyError(
                "Unknown installed skill '{0}'. Installed: {1}".format(
                    skill_name,
                    ", ".join(self.list_skill_names()) or "<none>",
                )
            )
        return record.skill

    def list_skill_names(self) -> List[str]:
        return sorted(self._installed_skills.keys())

    def list_skills(self) -> List[Dict[str, Any]]:
        skills: List[Dict[str, Any]] = []
        for name in self.list_skill_names():
            record = self._installed_skills[name]
            skills.append(
                {
                    "name": record.name,
                    "source": record.source,
                    "installed_at": record.installed_at,
                    "capabilities": record.skill.capability_names(),
                    "capability_count": len(record.skill.capability_names()),
                    "metadata": dict(record.metadata),
                }
            )
        return skills

    def _resolve_language_for_capability(
        self,
        spec: Mapping[str, Any],
        language: Optional[str],
    ) -> str:
        supported = _capability_supported_languages(spec)
        requested = self.profile.language_priority(language)
        if not requested:
            requested = ["en-us"]

        if not supported:
            return requested[0]

        for candidate in requested:
            for allowed in supported:
                if _is_language_match(candidate, allowed):
                    return candidate

        raise ValueError(
            "Capability does not support requested language. "
            "requested={0}, supported={1}".format(
                requested,
                supported,
            )
        )

    def list_capabilities(
        self,
        *,
        skill_name: Optional[str] = None,
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        names = [skill_name] if skill_name else self.list_skill_names()
        items: List[Dict[str, Any]] = []
        for name in names:
            skill = self.get_skill(name)
            for alias, spec in skill.capability_specs().items():
                supported = _capability_supported_languages(spec)
                try:
                    resolved = self._resolve_language_for_capability(spec, language)
                    language_ok = True
                except ValueError:
                    resolved = None
                    language_ok = False
                if language is not None and not language_ok:
                    continue

                items.append(
                    {
                        "skill_name": name,
                        "capability": alias,
                        "function_name": spec["function_name"],
                        "stream": bool(spec.get("stream", False)),
                        "media_type": spec.get("media_type", "application/json"),
                        "supported_languages": supported,
                        "selected_language": resolved,
                    }
                )
        return items

    def run(
        self,
        skill_name: str,
        capability_name: str,
        *args: Any,
        language: Optional[str] = None,
        target_node_id: Optional[str] = None,
        target_user_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        skill = self.get_skill(skill_name)
        specs = skill.capability_specs()
        spec = specs.get(capability_name)
        if spec is None:
            raise KeyError(
                "Unknown capability '{0}' for skill '{1}'".format(
                    capability_name,
                    skill_name,
                )
            )
        self._resolve_language_for_capability(spec, language)
        if target_node_id is not None or target_user_id is not None:
            resolved_node_id = self.resolve_target_node_id(
                node_id=target_node_id,
                user_id=target_user_id,
                required_functions=[str(spec["function_name"])],
                gateway_address=skill.gateway_address or self.gateway_address,
            )
            return self._run_spec_on_node(
                spec,
                resolved_node_id,
                *args,
                gateway_address=skill.gateway_address or self.gateway_address,
                **kwargs,
            )
        return skill.call(capability_name, *args, **kwargs)

    def run_any(
        self,
        capability_name: str,
        *args: Any,
        language: Optional[str] = None,
        target_node_id: Optional[str] = None,
        target_user_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        for name in self.list_skill_names():
            skill = self.get_skill(name)
            specs = skill.capability_specs()
            spec = specs.get(capability_name)
            if spec is None:
                continue
            try:
                self._resolve_language_for_capability(spec, language)
            except ValueError:
                continue
            if target_node_id is not None or target_user_id is not None:
                resolved_node_id = self.resolve_target_node_id(
                    node_id=target_node_id,
                    user_id=target_user_id,
                    required_functions=[str(spec["function_name"])],
                    gateway_address=skill.gateway_address or self.gateway_address,
                )
                return self._run_spec_on_node(
                    spec,
                    resolved_node_id,
                    *args,
                    gateway_address=skill.gateway_address or self.gateway_address,
                    **kwargs,
                )
            return skill.call(capability_name, *args, **kwargs)

        raise KeyError(
            "No installed skill can run capability '{0}' with language '{1}'".format(
                capability_name,
                language or self.profile.preferred_language,
            )
        )

    def run_ref(
        self,
        capability_ref: str,
        *args: Any,
        language: Optional[str] = None,
        target_node_id: Optional[str] = None,
        target_user_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Run with reference syntax:
        - "skill_name.capability"
        - "skill_name/capability"
        - "capability" (auto-select via run_any)
        """
        ref = str(capability_ref).strip()
        if not ref:
            raise ValueError("capability_ref cannot be empty")

        if "/" in ref:
            skill_name, capability = ref.split("/", 1)
            return self.run(
                skill_name.strip(),
                capability.strip(),
                *args,
                language=language,
                target_node_id=target_node_id,
                target_user_id=target_user_id,
                **kwargs,
            )
        if "." in ref:
            skill_name, capability = ref.split(".", 1)
            if skill_name in self._installed_skills:
                return self.run(
                    skill_name.strip(),
                    capability.strip(),
                    *args,
                    language=language,
                    target_node_id=target_node_id,
                    target_user_id=target_user_id,
                    **kwargs,
                )

        return self.run_any(
            ref,
            *args,
            language=language,
            target_node_id=target_node_id,
            target_user_id=target_user_id,
            **kwargs,
        )


__all__ = [
    "UserAgentProfile",
    "InstalledSkill",
    "RemoteAgentService",
]
