#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for asyncio grpc shutdown noise filter.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import logging

from easyremote.core.utils.asyncio_noise_filter import (
    install_asyncio_grpc_shutdown_noise_filter,
)


def _passes_logger_filters(record: logging.LogRecord) -> bool:
    logger = logging.getLogger("asyncio")
    for logger_filter in logger.filters:
        if not logger_filter.filter(record):
            return False
    return True


def test_asyncio_grpc_shutdown_noise_filter_blocks_known_poller_artifact():
    install_asyncio_grpc_shutdown_noise_filter()

    exc = BlockingIOError(35, "Resource temporarily unavailable")
    record = logging.LogRecord(
        name="asyncio",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Exception in callback PollerCompletionQueue._handle_events(...)",
        args=(),
        exc_info=(BlockingIOError, exc, None),
    )

    assert _passes_logger_filters(record) is False


def test_asyncio_grpc_shutdown_noise_filter_keeps_other_asyncio_errors():
    install_asyncio_grpc_shutdown_noise_filter()

    exc = RuntimeError("unexpected asyncio error")
    record = logging.LogRecord(
        name="asyncio",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Exception in callback some_other_callback",
        args=(),
        exc_info=(RuntimeError, exc, None),
    )

    assert _passes_logger_filters(record) is True

