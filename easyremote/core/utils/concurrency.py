#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Concurrency primitives for EasyRemote.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio
import threading
from typing import Any, Optional

from .exceptions import ConcurrencyBoundaryError


class LoopBoundAsyncLock:
    """
    Async lock that binds lazily to the first event loop that uses it.

    This avoids creating ``asyncio.Lock`` objects before an event loop exists
    while still enforcing a single-loop ownership model for safety.
    """

    def __init__(self, name: str = "loop-bound-lock") -> None:
        self._name = name
        self._bound_loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock: Optional[asyncio.Lock] = None
        self._guard = threading.Lock()

    def _get_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        current_loop_id = id(loop)

        with self._guard:
            if self._lock is None:
                self._lock = asyncio.Lock()
                self._bound_loop = loop
                return self._lock

            if self._bound_loop is not loop:
                raise ConcurrencyBoundaryError(
                    message=(
                        "Async lock '{0}' is bound to a different event loop".format(
                            self._name
                        )
                    ),
                    resource_name=self._name,
                    bound_loop_id=(
                        str(id(self._bound_loop)) if self._bound_loop is not None else None
                    ),
                    current_loop_id=str(current_loop_id),
                )

            return self._lock

    async def acquire(self) -> bool:
        """
        Acquire lock in current event loop.
        """
        lock = self._get_lock()
        await lock.acquire()
        return True

    def release(self) -> None:
        """
        Release lock in current event loop.
        """
        lock = self._get_lock()
        lock.release()

    def locked(self) -> bool:
        """
        Return whether lock is currently held.
        """
        lock = self._get_lock()
        return lock.locked()

    async def __aenter__(self) -> "LoopBoundAsyncLock":
        await self.acquire()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.release()


def create_loop_future() -> "asyncio.Future[Any]":
    """
    Create a future bound to the currently running event loop.
    """
    return asyncio.get_running_loop().create_future()
