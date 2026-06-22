"""Warm-process host for daemon ``host_stream`` executions.

The daemon opens this Unix socket directly, sends one host_stream
request envelope, and receives stream frames from the resident
:class:`HostServer`. There is no shell forwarder or alternate local
execution path here; the daemon owns admission, routing, receipts, and
stream validation.
"""

from .server import HostServer

__all__ = ["HostServer"]
