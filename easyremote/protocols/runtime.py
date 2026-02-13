#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Protocol runtime interfaces for EasyRemote.

This module defines the execution contract required by protocol adapters.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from abc import ABC, abstractmethod
from typing import Any, List

from .models import FunctionDescriptor, FunctionInvocation


class ProtocolRuntime(ABC):
    """
    Runtime contract for protocol adapters.

    Adapters stay transport/protocol-focused while execution concerns are
    delegated to a runtime implementation (e.g., gateway server).
    """

    @abstractmethod
    async def list_functions(self) -> List[FunctionDescriptor]:
        """
        Return all currently available remote functions.
        """

    @abstractmethod
    async def execute_invocation(self, invocation: FunctionInvocation) -> Any:
        """
        Execute a normalized invocation request and return result.
        """
