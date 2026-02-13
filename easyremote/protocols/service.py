#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
High-level service templates for MCP/A2A capability exposure.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union, cast

from .a2a import A2AProtocolAdapter
from .gateway import ProtocolGateway
from .mcp import MCPProtocolAdapter
from .models import FunctionDescriptor, FunctionInvocation, ProtocolName
from .runtime import ProtocolRuntime

_CAPABILITY_ATTR = "__easyremote_capability__"
_DEFAULT_RUNTIME_NAME = "easyremote-gateway"
_DEFAULT_RUNTIME_VERSION = "0.1.4"


def _normalize_tags(tags: Optional[Iterable[str]]) -> List[str]:
    if not tags:
        return []
    normalized: List[str] = []
    for item in tags:
        value = str(item).strip()
        if value:
            normalized.append(value)
    return sorted(set(normalized))


def _normalize_metadata(metadata: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if metadata is None:
        return {}
    return dict(metadata)


@dataclass(frozen=True)
class CapabilityDefinition:
    """
    Declarative metadata used by method-level capability decorators.
    """

    name: Optional[str] = None
    description: str = ""
    tags: Tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)


def agent_capability(
    func: Optional[Callable[..., Any]] = None,
    *,
    name: Optional[str] = None,
    description: str = "",
    tags: Optional[Iterable[str]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Union[Callable[[Callable[..., Any]], Callable[..., Any]], Callable[..., Any]]:
    """
    Method-level capability decorator for ProtocolServiceTemplate subclasses.
    """

    definition = CapabilityDefinition(
        name=name,
        description=description,
        tags=tuple(_normalize_tags(tags)),
        metadata=_normalize_metadata(metadata),
    )

    def decorator(target: Callable[..., Any]) -> Callable[..., Any]:
        setattr(target, _CAPABILITY_ATTR, definition)
        return target

    if func is not None and callable(func):
        return decorator(func)
    return decorator


class ServiceRuntime(ProtocolRuntime):
    """
    Built-in runtime registry for protocol services.
    """

    def __init__(
        self,
        *,
        runtime_name: str = _DEFAULT_RUNTIME_NAME,
        runtime_version: str = _DEFAULT_RUNTIME_VERSION,
    ) -> None:
        self.runtime_name = runtime_name
        self.runtime_version = runtime_version
        self._functions: Dict[str, Dict[str, Any]] = {}

    def register_function(
        self,
        func: Callable[..., Any],
        *,
        name: Optional[str] = None,
        description: str = "",
        tags: Optional[Iterable[str]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        node_ids: Optional[Sequence[str]] = None,
    ) -> str:
        function_name = (name or getattr(func, "__name__", "")).strip()
        if not function_name:
            raise ValueError("Function name cannot be empty")

        descriptor = FunctionDescriptor(
            name=function_name,
            description=description.strip(),
            node_ids=list(node_ids) if node_ids is not None else ["local"],
            tags=_normalize_tags(tags),
            metadata=_normalize_metadata(metadata),
        )
        self._functions[function_name] = {
            "callable": func,
            "descriptor": descriptor,
        }
        return function_name

    def capability(
        self,
        func: Optional[Callable[..., Any]] = None,
        *,
        name: Optional[str] = None,
        description: str = "",
        tags: Optional[Iterable[str]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        node_ids: Optional[Sequence[str]] = None,
    ) -> Union[Callable[[Callable[..., Any]], Callable[..., Any]], Callable[..., Any]]:
        """
        Decorator shortcut for function registration.
        """

        def decorator(target: Callable[..., Any]) -> Callable[..., Any]:
            self.register_function(
                target,
                name=name,
                description=description,
                tags=tags,
                metadata=metadata,
                node_ids=node_ids,
            )
            return target

        if func is not None and callable(func):
            return decorator(func)
        return decorator

    async def list_functions(self) -> List[FunctionDescriptor]:
        descriptors: List[FunctionDescriptor] = []
        for function_name in sorted(self._functions.keys()):
            descriptor = self._functions[function_name]["descriptor"]
            descriptors.append(
                FunctionDescriptor(
                    name=descriptor.name,
                    description=descriptor.description,
                    node_ids=list(descriptor.node_ids),
                    tags=list(descriptor.tags),
                    metadata=dict(descriptor.metadata),
                )
            )
        return descriptors

    async def execute_invocation(self, invocation: FunctionInvocation) -> Any:
        entry = self._functions.get(invocation.function_name)
        if entry is None:
            raise ValueError(f"Unknown function: {invocation.function_name}")

        func = entry["callable"]
        result = func(*invocation.args, **invocation.kwargs)

        if inspect.isawaitable(result):
            result = await result

        if inspect.isasyncgen(result):
            return [item async for item in result]
        if inspect.isgenerator(result):
            return list(result)

        return result


class ProtocolService:
    """
    Unified service facade for MCP/A2A protocol gateways.

    This class reduces setup to a single object with decorator registration and
    protocol dispatch helpers.
    """

    def __init__(
        self,
        *,
        runtime: Optional[ProtocolRuntime] = None,
        name: str = _DEFAULT_RUNTIME_NAME,
        version: str = _DEFAULT_RUNTIME_VERSION,
        enable_mcp: bool = True,
        enable_a2a: bool = True,
    ) -> None:
        self.runtime = runtime or ServiceRuntime(runtime_name=name, runtime_version=version)
        self._apply_runtime_identity(name=name, version=version)

        self._gateway = ProtocolGateway(runtime=self.runtime)
        if enable_mcp:
            self._gateway.register_adapter(MCPProtocolAdapter())
        if enable_a2a:
            self._gateway.register_adapter(A2AProtocolAdapter())

    def _apply_runtime_identity(self, *, name: str, version: str) -> None:
        setattr(self.runtime, "runtime_name", name)
        setattr(self.runtime, "runtime_version", version)

    def register_function(
        self,
        func: Callable[..., Any],
        *,
        name: Optional[str] = None,
        description: str = "",
        tags: Optional[Iterable[str]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        node_ids: Optional[Sequence[str]] = None,
    ) -> str:
        register_impl = getattr(self.runtime, "register_function", None)
        if register_impl is None or not callable(register_impl):
            raise TypeError(
                "Runtime does not support function registration. "
                "Use ServiceRuntime or provide a compatible custom runtime."
            )

        return cast(
            str,
            register_impl(
                func,
                name=name,
                description=description,
                tags=tags,
                metadata=metadata,
                node_ids=node_ids,
            ),
        )

    def capability(
        self,
        func: Optional[Callable[..., Any]] = None,
        *,
        name: Optional[str] = None,
        description: str = "",
        tags: Optional[Iterable[str]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        node_ids: Optional[Sequence[str]] = None,
    ) -> Union[Callable[[Callable[..., Any]], Callable[..., Any]], Callable[..., Any]]:
        """
        Decorator-based capability registration.
        """

        def decorator(target: Callable[..., Any]) -> Callable[..., Any]:
            self.register_function(
                target,
                name=name,
                description=description,
                tags=tags,
                metadata=metadata,
                node_ids=node_ids,
            )
            return target

        if func is not None and callable(func):
            return decorator(func)
        return decorator

    async def handle(
        self,
        protocol: Union[ProtocolName, str],
        payload: Any,
    ) -> Any:
        return await self._gateway.handle_request(protocol, payload)

    async def handle_mcp(self, payload: Any) -> Any:
        return await self.handle(ProtocolName.MCP, payload)

    async def handle_a2a(self, payload: Any) -> Any:
        return await self.handle(ProtocolName.A2A, payload)

    def supported_protocols(self) -> List[str]:
        return self._gateway.supported_protocols()


class ProtocolServiceTemplate(ProtocolService):
    """
    OOP template for MCP/A2A services using method decorators.
    """

    def __init__(
        self,
        *,
        runtime: Optional[ProtocolRuntime] = None,
        name: str = _DEFAULT_RUNTIME_NAME,
        version: str = _DEFAULT_RUNTIME_VERSION,
        enable_mcp: bool = True,
        enable_a2a: bool = True,
        auto_register: bool = True,
    ) -> None:
        super().__init__(
            runtime=runtime,
            name=name,
            version=version,
            enable_mcp=enable_mcp,
            enable_a2a=enable_a2a,
        )
        if auto_register:
            self.register_decorated_methods()

    def register_decorated_methods(self) -> None:
        """
        Scan class methods annotated with @agent_capability and register them.
        """
        registered_method_names: set[str] = set()
        for _, method in inspect.getmembers(self, predicate=callable):
            target = getattr(method, "__func__", method)
            definition = getattr(target, _CAPABILITY_ATTR, None)
            if not isinstance(definition, CapabilityDefinition):
                continue

            method_name = definition.name or getattr(method, "__name__", "")
            if not method_name or method_name in registered_method_names:
                continue

            self.register_function(
                method,
                name=method_name,
                description=definition.description,
                tags=definition.tags,
                metadata=definition.metadata,
            )
            registered_method_names.add(method_name)


class MCPService(ProtocolService):
    """
    MCP-only convenience facade built on ProtocolService.
    """

    def __init__(
        self,
        *,
        runtime: Optional[ProtocolRuntime] = None,
        name: str = _DEFAULT_RUNTIME_NAME,
        version: str = _DEFAULT_RUNTIME_VERSION,
    ) -> None:
        super().__init__(
            runtime=runtime,
            name=name,
            version=version,
            enable_mcp=True,
            enable_a2a=False,
        )


class A2AService(ProtocolService):
    """
    A2A-only convenience facade built on ProtocolService.
    """

    def __init__(
        self,
        *,
        runtime: Optional[ProtocolRuntime] = None,
        name: str = _DEFAULT_RUNTIME_NAME,
        version: str = _DEFAULT_RUNTIME_VERSION,
    ) -> None:
        super().__init__(
            runtime=runtime,
            name=name,
            version=version,
            enable_mcp=False,
            enable_a2a=True,
        )


__all__ = [
    "ServiceRuntime",
    "ProtocolService",
    "ProtocolServiceTemplate",
    "CapabilityDefinition",
    "agent_capability",
    "MCPService",
    "A2AService",
]
