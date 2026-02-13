#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Utility exports for EasyRemote core.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from .logger import ModernLogger
from .exceptions import *  # noqa: F401,F403 - maintain backward compatibility
from .exceptions import ExceptionFormatter, ExceptionTranslator
from .async_helpers import AsyncExecutionHelper
from .asyncio_noise_filter import install_asyncio_grpc_shutdown_noise_filter
from .concurrency import LoopBoundAsyncLock, create_loop_future

# Common formatter shortcuts
format_exception = ExceptionFormatter.format_exception
format_exception_chain = ExceptionFormatter.format_exception_chain
format_exception_summary = ExceptionFormatter.format_exception_summary

__all__ = [
    "ModernLogger",
    "AsyncExecutionHelper",
    "install_asyncio_grpc_shutdown_noise_filter",
    "ExceptionFormatter",
    "ExceptionTranslator",
    "LoopBoundAsyncLock",
    "create_loop_future",
    "format_exception",
    "format_exception_chain",
    "format_exception_summary",
]
