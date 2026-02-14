#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Regression tests for protocol runtime execution on the gateway.

In particular, stream-mode invocations must return an async iterator rather than
attempting to `await` an async generator.
"""

import asyncio

from easyremote.core.nodes.server import Server
from easyremote.protocols import FunctionInvocation


def test_gateway_execute_invocation_stream_returns_async_iterator():
    server = Server(
        port=18080,
        enable_monitoring=False,
        enable_analytics=False,
    )

    invocation = FunctionInvocation.from_arguments(
        function_name="noop",
        arguments={},
        stream=True,
    )

    result = asyncio.run(server.execute_invocation(invocation))
    assert hasattr(result, "__aiter__")


def test_gateway_execute_invocation_stream_load_balancing_returns_async_iterator():
    server = Server(
        port=18081,
        enable_monitoring=False,
        enable_analytics=False,
    )

    invocation = FunctionInvocation.from_arguments(
        function_name="noop",
        arguments={},
        load_balancing=True,
        stream=True,
    )

    result = asyncio.run(server.execute_invocation(invocation))
    assert hasattr(result, "__aiter__")

