"""Warm-process host (SPEC §4.1 D2, transition design).

The daemon's shell executor spawns a thin forwarder per invocation;
the forwarder relays the rendered argv values over a Unix socket to
the resident :class:`HostServer`, where the user's functions — and
their loaded models — stay warm. Replaced wholesale by the daemon
host-attach protocol when Cli PR-1 lands; nothing outside this
package knows the difference.
"""

from .server import HostServer

__all__ = ["HostServer"]
