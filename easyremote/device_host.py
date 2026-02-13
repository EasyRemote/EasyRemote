#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
User-device host for installing remote agent capabilities as local node functions.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

from .skills import RemoteSkill

_DEVICE_ACTION_ATTR = "__easyremote_device_action__"


def device_action(
    func: Optional[Callable[..., Any]] = None,
    *,
    name: Optional[str] = None,
    description: str = "",
    metadata: Optional[Mapping[str, Any]] = None,
) -> Any:
    """
    Mark a function as a device action for automatic sandbox discovery.

    Supports both ``@device_action`` and ``@device_action(name=...)`` forms.
    """

    def decorator(target: Callable[..., Any]) -> Callable[..., Any]:
        setattr(target, _DEVICE_ACTION_ATTR, {
            "name": name or target.__name__,
            "description": str(description),
            "metadata": dict(metadata or {}),
        })
        return target

    if func is not None and callable(func):
        return decorator(func)
    return decorator


def _normalize_tags(values: Optional[Sequence[Any]]) -> Set[str]:
    if values is None:
        return set()
    tags: Set[str] = set()
    for item in values:
        value = str(item).strip()
        if value:
            tags.add(value)
    return tags


def _parse_payload_object(payload: Union[str, bytes, Mapping[str, Any]]) -> Dict[str, Any]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        parsed = json.loads(payload)
    elif isinstance(payload, Mapping):
        parsed = dict(payload)
    else:
        raise TypeError("payload must be dict, json str, or utf-8 bytes")
    if not isinstance(parsed, dict):
        raise ValueError("payload must decode to object")
    return parsed


@dataclass
class DeviceAction:
    """
    User-approved local action that can be bound to remote capabilities.
    """

    name: str
    handler: Callable[..., Any]
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InstalledDeviceSkill:
    """
    Installed remote skill mapped to local device actions.
    """

    name: str
    installed_at: str
    source: str
    capabilities: Dict[str, Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)


class UserDeviceCapabilityHost:
    """
    Install remote skill payloads and register local functions on a compute node.

    Flow:
    1. Register user-approved local actions (camera/photo/video/etc).
    2. Receive remote skill payload from server-side agent.
    3. Bind payload capabilities to local actions and register on node.
    """

    def __init__(
        self,
        node: Any,
        *,
        auto_refresh_registration: bool = True,
        refresh_timeout_seconds: float = 8.0,
        prefer_transferred_code: bool = False,
        allow_transferred_code: bool = False,
        auto_consent: bool = False,
        consent_callback: Optional[Callable[[Dict[str, Any]], bool]] = None,
        max_runtime_modules: int = 8,
        max_runtime_module_source_bytes: int = 200_000,
        max_total_runtime_source_bytes: int = 800_000,
    ) -> None:
        self.node = node
        self.auto_refresh_registration = bool(auto_refresh_registration)
        self.refresh_timeout_seconds = float(refresh_timeout_seconds)
        # Default behavior is to bind remote capabilities to user-approved local
        # actions (device_action). Enable this to prefer runtime code shipped
        # inside the skill payload (code_binding + runtime_modules).
        self.prefer_transferred_code = bool(prefer_transferred_code)
        # Remote code execution is high risk; keep it opt-in by default.
        self.allow_transferred_code = bool(allow_transferred_code)
        # Consent hook for user-side approval (install-time).
        self.auto_consent = bool(auto_consent)
        self.consent_callback = consent_callback
        # Basic payload guardrails (do not replace sandboxing/signing).
        self.max_runtime_modules = max(0, int(max_runtime_modules))
        self.max_runtime_module_source_bytes = max(0, int(max_runtime_module_source_bytes))
        self.max_total_runtime_source_bytes = max(0, int(max_total_runtime_source_bytes))
        self._actions: Dict[str, DeviceAction] = {}
        self._installed: Dict[str, InstalledDeviceSkill] = {}
        self._sandbox_modules: List[ModuleType] = []

    def _load_runtime_modules(self, payload_obj: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Load transferred runtime code modules from payload.

        Payload extension:
        - runtime_modules: [
            {
              "module_id": "camera-runtime-v1",
              "language": "python",
              "source": "def take_photo(...): ..."
            }
          ]
        """
        runtime_modules = payload_obj.get("runtime_modules", [])
        if runtime_modules is None:
            return {}
        if not isinstance(runtime_modules, list):
            raise ValueError("runtime_modules must be a list")
        if self.max_runtime_modules and len(runtime_modules) > self.max_runtime_modules:
            raise ValueError(
                "runtime_modules too large: count={0}, max={1}".format(
                    len(runtime_modules),
                    self.max_runtime_modules,
                )
            )

        loaded: Dict[str, Dict[str, Any]] = {}
        total_source_bytes = 0
        for item in runtime_modules:
            if not isinstance(item, Mapping):
                raise ValueError("runtime_modules entries must be objects")
            module_id = str(item.get("module_id", "")).strip()
            if not module_id:
                raise ValueError("runtime module requires non-empty module_id")

            language = str(item.get("language", "python")).strip().lower()
            if language not in {"python", "py"}:
                raise ValueError(
                    "Unsupported runtime module language '{0}' for module '{1}'".format(
                        language, module_id
                    )
                )

            source = item.get("source")
            if not isinstance(source, str) or not source.strip():
                raise ValueError(
                    "runtime module '{0}' requires non-empty source".format(module_id)
                )
            source_bytes = source.encode("utf-8")
            if self.max_runtime_module_source_bytes and len(source_bytes) > self.max_runtime_module_source_bytes:
                raise ValueError(
                    "runtime module '{0}' source too large: bytes={1}, max={2}".format(
                        module_id,
                        len(source_bytes),
                        self.max_runtime_module_source_bytes,
                    )
                )
            total_source_bytes += len(source_bytes)
            if self.max_total_runtime_source_bytes and total_source_bytes > self.max_total_runtime_source_bytes:
                raise ValueError(
                    "runtime module sources too large: bytes={0}, max={1}".format(
                        total_source_bytes,
                        self.max_total_runtime_source_bytes,
                    )
                )

            expected_sha256 = item.get("sha256")
            if expected_sha256 is not None:
                expected = str(expected_sha256).strip().lower()
                if expected:
                    actual = hashlib.sha256(source_bytes).hexdigest()
                    if actual != expected:
                        raise ValueError(
                            "runtime module '{0}' sha256 mismatch: expected={1}, actual={2}".format(
                                module_id,
                                expected,
                                actual,
                            )
                        )

            namespace: Dict[str, Any] = {"__builtins__": __builtins__}
            exec(source, namespace, namespace)
            loaded[module_id] = namespace

        return loaded

    def _resolve_transferred_handler(
        self,
        capability_spec: Mapping[str, Any],
        runtime_modules: Mapping[str, Mapping[str, Any]],
    ) -> Tuple[Optional[Callable[..., Any]], Optional[Dict[str, str]]]:
        metadata = capability_spec.get("metadata")
        if not isinstance(metadata, Mapping):
            return (None, None)

        binding = metadata.get("code_binding")
        module_id: Optional[str] = None
        export_name: Optional[str] = None

        if isinstance(binding, Mapping):
            module_id_raw = binding.get("module_id")
            export_raw = binding.get("export")
            if module_id_raw is not None:
                module_id = str(module_id_raw).strip() or None
            if export_raw is not None:
                export_name = str(export_raw).strip() or None
        else:
            module_id_raw = metadata.get("runtime_module")
            export_raw = metadata.get("runtime_export")
            if module_id_raw is not None:
                module_id = str(module_id_raw).strip() or None
            if export_raw is not None:
                export_name = str(export_raw).strip() or None

        if not module_id or not export_name:
            return (None, None)

        module = runtime_modules.get(module_id)
        if module is None:
            raise KeyError(
                "Runtime module '{0}' not found in payload".format(module_id)
            )
        handler = module.get(export_name)
        if not callable(handler):
            raise KeyError(
                "Runtime export '{0}' in module '{1}' is not callable".format(
                    export_name,
                    module_id,
                )
            )
        return (
            handler,
            {"module_id": module_id, "export": export_name},
        )

    def register_action(
        self,
        action_name: str,
        handler: Callable[..., Any],
        *,
        description: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        name = str(action_name).strip()
        if not name:
            raise ValueError("action_name cannot be empty")
        if not callable(handler):
            raise ValueError("handler must be callable")

        self._actions[name] = DeviceAction(
            name=name,
            handler=handler,
            description=str(description).strip(),
            metadata=dict(metadata or {}),
        )

    def unregister_action(self, action_name: str) -> bool:
        return self._actions.pop(str(action_name).strip(), None) is not None

    def list_actions(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {
                "description": action.description,
                "metadata": dict(action.metadata),
            }
            for name, action in sorted(self._actions.items())
        }

    def load_sandbox(self, path: Union[str, Path]) -> int:
        """
        Scan a directory for ``*.py`` modules containing ``@device_action``
        decorated functions and register them automatically.

        Returns the number of actions registered.
        """
        sandbox_dir = Path(path)
        if not sandbox_dir.is_dir():
            raise NotADirectoryError(
                "sandbox path is not a directory: {0}".format(sandbox_dir)
            )
        count = 0
        for py_file in sorted(sandbox_dir.glob("*.py")):
            stem = py_file.stem
            module_name = "_easyremote_sandbox_{0}".format(stem)
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            self._sandbox_modules.append(mod)
            for attr_name in dir(mod):
                obj = getattr(mod, attr_name, None)
                if not callable(obj):
                    continue
                info = getattr(obj, _DEVICE_ACTION_ATTR, None)
                if info is None:
                    continue
                action_name = str(info.get("name", attr_name)).strip()
                self.register_action(
                    action_name,
                    obj,
                    description=str(info.get("description", "")),
                    metadata=info.get("metadata"),
                )
                count += 1
        return count

    def _resolve_action(self, capability_alias: str, capability_spec: Mapping[str, Any]) -> DeviceAction:
        metadata = capability_spec.get("metadata")
        action_name: Optional[str] = None
        if isinstance(metadata, Mapping):
            raw = metadata.get("device_action")
            if raw is not None:
                action_name = str(raw).strip()
        if not action_name:
            action_name = capability_alias

        action = self._actions.get(action_name)
        if action is None:
            raise KeyError(
                "No local device action '{0}' for capability '{1}'. "
                "Register it with host.register_action(...).".format(
                    action_name,
                    capability_alias,
                )
            )
        return action

    def _try_refresh_registration(self) -> bool:
        if not self.auto_refresh_registration:
            return False

        refresh = getattr(self.node, "refresh_gateway_registration_now", None)
        if callable(refresh):
            return bool(refresh(timeout_seconds=self.refresh_timeout_seconds))
        return False

    def install_skill(
        self,
        payload: Union[str, bytes, Mapping[str, Any]],
        *,
        skill_name: Optional[str] = None,
        source: str = "remote-agent",
        metadata: Optional[Mapping[str, Any]] = None,
        gateway_address: Optional[str] = None,
    ) -> str:
        """
        Install one remote skill and register mapped local functions to compute node.
        """
        payload_obj = _parse_payload_object(payload)
        skill = RemoteSkill.from_pipeline(payload_obj, gateway_address=gateway_address)
        payload_runtime_modules = payload_obj.get("runtime_modules")
        payload_runtime_module_ids: List[str] = []
        if isinstance(payload_runtime_modules, list):
            for item in payload_runtime_modules:
                if not isinstance(item, Mapping):
                    continue
                module_id = str(item.get("module_id", "")).strip()
                if module_id:
                    payload_runtime_module_ids.append(module_id)
        payload_runtime_module_ids = sorted(set(payload_runtime_module_ids))

        runtime_modules: Optional[Dict[str, Dict[str, Any]]] = None

        def _runtime_modules() -> Dict[str, Dict[str, Any]]:
            nonlocal runtime_modules
            if runtime_modules is None:
                runtime_modules = self._load_runtime_modules(payload_obj)
            return runtime_modules
        target_name = str(skill_name or skill.name).strip()
        if not target_name:
            raise ValueError("skill_name cannot be empty")

        registered_functions = getattr(self.node, "registered_functions", {})
        existing_names = set(getattr(registered_functions, "keys", lambda: [])())

        installed_capabilities: Dict[str, Dict[str, Any]] = {}
        for alias, spec in skill.capability_specs().items():
            action: Optional[DeviceAction] = None
            binding: Optional[Dict[str, str]] = None
            metadata_obj = spec.get("metadata")

            requires_user_consent = False
            if isinstance(metadata_obj, Mapping):
                requires_user_consent = bool(metadata_obj.get("requires_user_consent", False))
            if requires_user_consent:
                allow = self.auto_consent
                if self.consent_callback is not None:
                    allow = bool(
                        self.consent_callback(
                            {
                                "skill_name": target_name,
                                "capability": alias,
                                "function_name": spec.get("function_name"),
                                "metadata": dict(metadata_obj),
                            }
                        )
                    )
                if not allow:
                    raise PermissionError(
                        "User consent required for capability '{0}' in skill '{1}'".format(
                            alias,
                            target_name,
                        )
                    )

            def _has_code_binding() -> bool:
                if not isinstance(metadata_obj, Mapping):
                    return False
                binding_obj = metadata_obj.get("code_binding")
                if isinstance(binding_obj, Mapping):
                    return True
                return bool(metadata_obj.get("runtime_module")) or bool(
                    metadata_obj.get("runtime_export")
                )

            def _try_code_transfer() -> Tuple[Optional[Callable[..., Any]], Optional[Dict[str, str]]]:
                if not _has_code_binding():
                    return (None, None)
                if not self.allow_transferred_code:
                    return (None, None)
                try:
                    return self._resolve_transferred_handler(spec, _runtime_modules())
                except KeyError:
                    # Bad binding/module payload. Fall back to device_action mapping if available.
                    return (None, None)

            if self.prefer_transferred_code:
                transferred_handler, binding = _try_code_transfer()
                if transferred_handler is not None:
                    handler = transferred_handler
                    action_name = None
                    binding_mode = "code_transfer"
                else:
                    action = self._resolve_action(alias, spec)
                    handler = action.handler
                    action_name = action.name
                    binding_mode = "device_action"
            else:
                try:
                    action = self._resolve_action(alias, spec)
                    handler = action.handler
                    action_name = action.name
                    binding_mode = "device_action"
                except KeyError:
                    if _has_code_binding() and not self.allow_transferred_code:
                        raise PermissionError(
                            "Capability '{0}' requires transferred code, but allow_transferred_code=False".format(
                                alias,
                            )
                        )
                    transferred_handler, binding = _try_code_transfer()
                    if transferred_handler is not None:
                        handler = transferred_handler
                        action_name = None
                        binding_mode = "code_transfer"
                    else:
                        raise

            function_name = str(spec["function_name"]).strip()
            if not function_name:
                raise ValueError("function_name cannot be empty")

            timeout = spec.get("timeout")
            tag_values: Set[str] = {"remote-agent", target_name}
            if isinstance(metadata_obj, Mapping):
                tag_values.update(_normalize_tags(metadata_obj.get("tags")))
            if spec.get("stream"):
                tag_values.add("stream")
            if binding_mode == "code_transfer":
                tag_values.add("code-transfer")

            if function_name not in existing_names:
                if binding_mode == "code_transfer":
                    description = "Transferred runtime code from remote agent"
                else:
                    description = (
                        action.description
                        if action is not None and action.description
                        else "Installed by remote agent"
                    )
                self.node.register(
                    handler,
                    name=function_name,
                    timeout_seconds=timeout,
                    tags=tag_values,
                    description=description,
                )
                existing_names.add(function_name)

            installed_capabilities[alias] = {
                "function_name": function_name,
                "action_name": action_name,
                "binding_mode": binding_mode,
                "code_binding": dict(binding) if binding is not None else None,
                "stream": bool(spec.get("stream", False)),
                "media_type": spec.get("media_type", "application/json"),
                "metadata": dict(metadata_obj) if isinstance(metadata_obj, Mapping) else {},
            }

        self._installed[target_name] = InstalledDeviceSkill(
            name=target_name,
            installed_at=datetime.now(timezone.utc).isoformat(),
            source=str(source).strip() or "remote-agent",
            capabilities=installed_capabilities,
            metadata={
                **dict(metadata or {}),
                "runtime_modules": (
                    sorted(runtime_modules.keys())
                    if runtime_modules is not None
                    else payload_runtime_module_ids
                ),
            },
        )
        self._try_refresh_registration()
        return target_name

    def register_skill_endpoints(
        self,
        *,
        install_name: str = "device.install_remote_skill",
        list_name: str = "device.list_installed_skills",
        install_tags: Optional[Set[str]] = None,
        list_tags: Optional[Set[str]] = None,
        source: str = "remote-agent",
    ) -> None:
        """
        Register standard skill-management endpoints on the compute node.

        This eliminates the need to manually define ``install_remote_skill``
        and ``list_installed_skills`` handlers in user code.
        """
        host = self
        node = self.node
        node_id_attr = getattr(node, "node_id", None)

        def _install_remote_skill(
            skill_payload: Dict[str, Any],
        ) -> Dict[str, Any]:
            name = host.install_skill(skill_payload, source=source)
            result: Dict[str, Any] = {
                "installed_skill": name,
                "installed_skills": host.list_installed_skills(),
            }
            if node_id_attr is not None:
                result["node_id"] = node_id_attr
            registered = getattr(node, "registered_functions", None)
            if registered is not None:
                result["node_functions"] = sorted(registered.keys())
            return result

        def _list_installed_skills() -> Dict[str, Any]:
            return host.list_installed_skills()

        node.register(
            _install_remote_skill,
            name=install_name,
            tags=install_tags or {"device", "skill", "installer"},
        )
        node.register(
            _list_installed_skills,
            name=list_name,
            tags=list_tags or {"device", "skill"},
        )

    def uninstall_skill(self, skill_name: str) -> bool:
        return self._installed.pop(str(skill_name).strip(), None) is not None

    def list_installed_skills(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {
                "source": skill.source,
                "installed_at": skill.installed_at,
                "capabilities": dict(skill.capabilities),
                "metadata": dict(skill.metadata),
            }
            for name, skill in sorted(self._installed.items())
        }


__all__ = [
    "device_action",
    "DeviceAction",
    "InstalledDeviceSkill",
    "UserDeviceCapabilityHost",
]
