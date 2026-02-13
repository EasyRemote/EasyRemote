#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for concurrency utility primitives.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import asyncio

import pytest

from easyremote.core.utils.concurrency import LoopBoundAsyncLock, create_loop_future
from easyremote.core.utils.exceptions import ConcurrencyBoundaryError


async def _acquire_once(lock: LoopBoundAsyncLock) -> None:
    async with lock:
        assert lock.locked() is True


def test_loop_bound_lock_works_within_single_loop():
    lock = LoopBoundAsyncLock(name="test-lock-single-loop")

    async def run_case():
        await _acquire_once(lock)
        assert lock.locked() is False

    asyncio.run(run_case())


def test_loop_bound_lock_rejects_cross_loop_reuse():
    lock = LoopBoundAsyncLock(name="test-lock-cross-loop")

    asyncio.run(_acquire_once(lock))

    with pytest.raises(ConcurrencyBoundaryError):
        asyncio.run(_acquire_once(lock))


def test_create_loop_future_binds_to_current_loop():
    async def run_case():
        future = create_loop_future()
        assert future.get_loop() is asyncio.get_running_loop()

    asyncio.run(run_case())
