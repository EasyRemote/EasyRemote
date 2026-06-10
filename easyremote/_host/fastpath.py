"""Lazy compilation of the C fast forwarder (the low-latency path).

The Python shim costs ~50-60ms of interpreter spawn per invocation;
the native forwarder costs single-digit milliseconds. Compilation
happens once per source revision, cached under
``~/.easynet/easyremote/bin``, and silently falls back to the Python
shim when no C compiler is available (``EASYREMOTE_FORWARDER=python``
forces the fallback).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

__all__ = ["forwarder_command"]

_SOURCE = Path(__file__).with_name("forward.c")
_BIN_DIR = Path.home() / ".easynet" / "easyremote" / "bin"


def forwarder_command(socket_path: Path, fn_name: str) -> str:
    """The ability.json ``command`` line for one registered function."""
    binary = _ensure_binary()
    if binary is not None:
        return f"{binary} {socket_path} {fn_name}"
    return f"{sys.executable} -m easyremote._host.forward {socket_path} {fn_name}"


def _ensure_binary() -> Path | None:
    if os.environ.get("EASYREMOTE_FORWARDER") == "python":
        return None
    try:
        source = _SOURCE.read_bytes()
    except OSError:
        return None
    digest = hashlib.sha256(source).hexdigest()[:16]
    binary = _BIN_DIR / f"easyremote-forward-{digest}"
    if binary.exists():
        return binary

    compiler = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if compiler is None:
        return None
    _BIN_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=_BIN_DIR, delete=False) as scratch:
        scratch_path = Path(scratch.name)
    try:
        subprocess.run(
            [compiler, "-O2", "-o", str(scratch_path), str(_SOURCE)],
            capture_output=True,
            check=True,
        )
        scratch_path.chmod(0o755)
        scratch_path.replace(binary)  # atomic publish
        return binary
    except subprocess.CalledProcessError:
        scratch_path.unlink(missing_ok=True)
        return None
