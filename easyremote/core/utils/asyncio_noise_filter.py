#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Asyncio logging noise filters for known third-party shutdown artifacts.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import logging
import threading

_FILTER_INSTALL_LOCK = threading.Lock()
_FILTER_INSTALLED = False


class _GrpcAioPollerShutdownNoiseFilter(logging.Filter):
    """
    Filter known grpc.aio poller shutdown warnings from asyncio logger.

    This targets a grpc.aio shutdown artifact where asyncio logs:
    "Exception in callback PollerCompletionQueue._handle_events(...)"
    with BlockingIOError(EAGAIN/EWOULDBLOCK) during process teardown.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not record.exc_info:
            return True

        exception = record.exc_info[1]
        if not isinstance(exception, BlockingIOError):
            return True

        # 11: EAGAIN/Linux, 35: EWOULDBLOCK/macOS
        if exception.errno not in (11, 35):
            return True

        message = record.getMessage()
        if "PollerCompletionQueue._handle_events" in message:
            return False

        return True


def install_asyncio_grpc_shutdown_noise_filter() -> None:
    """
    Install process-wide asyncio logger filter for grpc.aio shutdown noise.
    """
    global _FILTER_INSTALLED

    if _FILTER_INSTALLED:
        return

    with _FILTER_INSTALL_LOCK:
        if _FILTER_INSTALLED:
            return

        logging.getLogger("asyncio").addFilter(
            _GrpcAioPollerShutdownNoiseFilter()
        )
        _FILTER_INSTALLED = True

