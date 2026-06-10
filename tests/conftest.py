"""Shared fixtures."""

import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def short_tmp() -> Path:
    """A short-prefix temp dir for AF_UNIX sockets.

    pytest's tmp_path nests deep enough to blow the ~104-byte
    sun_path limit on macOS; sockets must bind under /tmp instead.
    """
    path = Path(tempfile.mkdtemp(prefix="er-", dir="/tmp"))
    yield path
    shutil.rmtree(path, ignore_errors=True)
