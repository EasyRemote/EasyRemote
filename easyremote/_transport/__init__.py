"""Private transport layer: ctypes binding over libeasynet_cli (ABI v3).

Everything here is JSON-in/JSON-out plumbing. Protocol semantics
(seven-tuple construction, receipts, terminal-frame interpretation)
live in the public layers above; this package never invents them.
"""

from .abi import ABI_VERSION, Library, library
from .session import BidiChannel, DaemonProcess, FrameStream, Transport

__all__ = [
    "ABI_VERSION",
    "BidiChannel",
    "DaemonProcess",
    "FrameStream",
    "Library",
    "Transport",
    "library",
]
