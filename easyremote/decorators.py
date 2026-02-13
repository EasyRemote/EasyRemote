#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Decorator helpers for EasyRemote function invocation.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio
import functools
import os
from concurrent.futures import Future as ConcurrentFuture
from typing import Any, Callable, Optional, TypeVar, Union, cast

from .core.utils.exceptions import ExceptionTranslator, RemoteExecutionError

T = TypeVar("T", bound=Callable[..., Any])


def _resolve_global_server() -> Any:
    """
    Resolve the global server lazily to avoid importing heavy modules at import time.
    """
    from .core.nodes.server import Server

    return Server.get_global_instance()


def _resolve_default_client() -> Any:
    """
    Resolve a client for standalone consumer processes.

    Resolution order:
    1. Previously configured default client (`set_default_gateway`)
    2. `EASYREMOTE_GATEWAY` / `EASYREMOTE_GATEWAY_ADDRESS` environment variable
    """
    from .core.nodes.client import get_default_client, set_default_gateway

    client = get_default_client()
    if client is not None:
        return client

    gateway_address = os.getenv("EASYREMOTE_GATEWAY") or os.getenv(
        "EASYREMOTE_GATEWAY_ADDRESS"
    )
    if gateway_address:
        return set_default_gateway(gateway_address)

    return None


class RemoteFunction:
    """
    Callable wrapper that routes a local function call to EasyRemote server.
    """

    server_resolver: Callable[[], Any] = staticmethod(_resolve_global_server)
    client_resolver: Callable[[], Any] = staticmethod(_resolve_default_client)

    def __init__(
        self,
        func: Callable[..., Any],
        node_id: Optional[str] = None,
        function_name: Optional[str] = None,
        timeout: Optional[float] = None,
        is_stream: bool = False,
        is_async: bool = False,
        load_balancing: Union[bool, str, dict] = False,
        gateway_address: Optional[str] = None,
    ) -> None:
        self.func = func
        self.node_id = node_id
        self.function_name = function_name or func.__name__
        self.timeout = timeout
        self.is_stream = is_stream
        self.is_async = is_async
        self.load_balancing = load_balancing
        self.gateway_address = gateway_address
        functools.update_wrapper(self, func)

    def _get_server(self) -> Any:
        """Resolve in-process gateway server (if available)."""
        return self.server_resolver()

    def _get_client(self) -> Any:
        """Resolve standalone client backend (if available)."""
        client = self.client_resolver()
        if client is not None:
            return client

        if self.gateway_address:
            from .core.nodes.client import set_default_gateway

            return set_default_gateway(self.gateway_address)

        return None

    @staticmethod
    def _resolve_server_loop(server: Any) -> Optional[asyncio.AbstractEventLoop]:
        """
        Best-effort resolve of server-owned event loop.

        For background server mode, EasyRemote stores the serving loop on
        ``server._event_loop``. If this loop differs from the caller's loop we
        must dispatch coroutines to that loop to avoid concurrency-boundary
        violations (e.g., loop-bound async locks).
        """
        loop = getattr(server, "_event_loop", None)
        if isinstance(loop, asyncio.AbstractEventLoop):
            return loop
        return None

    async def _await_server_coroutine(
        self,
        server: Any,
        coroutine: Any,
    ) -> Any:
        """
        Await server coroutine in the correct event loop context.
        """
        current_loop = asyncio.get_running_loop()
        server_loop = self._resolve_server_loop(server)

        if (
            server_loop is not None
            and server_loop.is_running()
            and server_loop is not current_loop
        ):
            threaded_future: ConcurrentFuture = asyncio.run_coroutine_threadsafe(
                coroutine, server_loop
            )
            wrapped = asyncio.wrap_future(threaded_future)
            if self.timeout is not None:
                return await asyncio.wait_for(wrapped, timeout=self.timeout)
            return await wrapped

        if self.timeout is not None:
            return await asyncio.wait_for(coroutine, timeout=self.timeout)
        return await coroutine

    def _build_client_execution_context(self) -> Any:
        """
        Build client execution context for standalone client mode.
        """
        from .core.nodes.client import ExecutionContext, ExecutionStrategy

        timeout_ms = int(self.timeout * 1000) if self.timeout is not None else None

        # Direct node targeting mode.
        if self.node_id and not self.load_balancing:
            return ExecutionContext(
                function_name=self.function_name,
                strategy=ExecutionStrategy.DIRECT_TARGET,
                preferred_node_ids=[self.node_id],
                timeout_ms=timeout_ms,
            )

        # Load-balanced mode.
        requirements = None
        cost_limit = None
        if isinstance(self.load_balancing, dict):
            requirements = self.load_balancing.get("requirements")
            cost_limit = self.load_balancing.get("cost_limit")

        return ExecutionContext(
            function_name=self.function_name,
            strategy=ExecutionStrategy.LOAD_BALANCED,
            timeout_ms=timeout_ms,
            requirements=requirements,
            cost_limit=cost_limit,
        )

    async def _invoke_via_client(self, client: Any, *args: Any, **kwargs: Any) -> Any:
        """
        Execute call via standalone client backend.

        `DistributedComputingClient` is synchronous; use `asyncio.to_thread` to
        keep async call sites non-blocking.
        """
        context = self._build_client_execution_context()
        execution_result = await asyncio.to_thread(
            client.execute_with_context,
            context,
            *args,
            **kwargs
        )
        return execution_result.result

    async def _invoke_via_server(self, server: Any, *args: Any, **kwargs: Any) -> Any:
        """
        Execute call via in-process server backend.
        """
        if self.load_balancing:
            if not hasattr(server, "execute_function_with_load_balancing"):
                raise RemoteExecutionError(
                    function_name=self.function_name,
                    message="Server does not support load balancing execution",
                )
            result = server.execute_function_with_load_balancing(
                self.function_name,
                self.load_balancing,
                *args,
                **kwargs
            )
        else:
            if not hasattr(server, "execute_function"):
                raise RemoteExecutionError(
                    function_name=self.function_name,
                    message="Server does not support direct function execution",
                )
            result = server.execute_function(
                self.node_id,
                self.function_name,
                *args,
                **kwargs
            )

        if asyncio.iscoroutine(result):
            return await self._await_server_coroutine(server, result)
        return result

    async def _invoke(self, *args: Any, **kwargs: Any) -> Any:
        """
        Execute one remote invocation.

        Backend precedence:
        1. In-process server backend (same process gateway)
        2. Standalone client backend (default client / gateway address / env)
        """
        try:
            server = self._get_server()
            if server is not None:
                return await self._invoke_via_server(server, *args, **kwargs)

            client = self._get_client()
            if client is not None:
                return await self._invoke_via_client(client, *args, **kwargs)

            raise RemoteExecutionError(
                function_name=self.function_name,
                message=(
                    "No EasyRemote execution backend available. "
                    "Start a local Server, call set_default_gateway(...), "
                    "set EASYREMOTE_GATEWAY, or pass gateway_address to @remote."
                )
            )
        except Exception as exc:
            raise ExceptionTranslator.as_remote_execution_error(
                exc,
                function_name=self.function_name,
            ) from exc

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """
        Sync-friendly call entry.

        Behavior:
        - No running loop: blocks until completion via asyncio.run.
        - Running loop: returns coroutine for caller to await.
        """
        coroutine = self._invoke(*args, **kwargs)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)
        return coroutine

    async def __call_async__(self, *args: Any, **kwargs: Any) -> Any:
        """
        Async call entry.
        """
        return await self._invoke(*args, **kwargs)


def register(
    *,
    node_id: Optional[str] = None,
    function_name: Optional[str] = None,
    timeout: Optional[float] = None,
    stream: bool = False,
    async_func: bool = False,
    load_balancing: Union[bool, str, dict] = False,
    gateway_address: Optional[str] = None,
) -> Callable[[T], T]:
    """
    Decorate a function as an EasyRemote remote call proxy.
    """

    def decorator(func: T) -> T:
        remote_function = RemoteFunction(
            func,
            node_id=node_id,
            function_name=function_name,
            timeout=timeout,
            is_stream=stream,
            is_async=async_func,
            load_balancing=load_balancing,
            gateway_address=gateway_address,
        )

        if async_func:

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await remote_function.__call_async__(*args, **kwargs)

            return cast(T, async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return remote_function(*args, **kwargs)

        return cast(T, sync_wrapper)

    return decorator


def remote(
    func: Optional[Callable[..., Any]] = None,
    *,
    node_id: Optional[str] = None,
    function_name: Optional[str] = None,
    timeout: Optional[float] = None,
    stream: bool = False,
    async_func: bool = False,
    load_balancing: Union[bool, str, dict] = False,
    gateway_address: Optional[str] = None,
) -> Union[Callable[[T], T], T]:
    """
    Public decorator entry supporting both:
    - @remote
    - @remote(...)
    """
    decorator = register(
        node_id=node_id,
        function_name=function_name,
        timeout=timeout,
        stream=stream,
        async_func=async_func,
        load_balancing=load_balancing,
        gateway_address=gateway_address,
    )

    if func is not None and callable(func):
        return decorator(cast(T, func))
    return decorator
