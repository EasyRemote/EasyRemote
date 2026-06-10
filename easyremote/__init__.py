"""EasyRemote — turn a local function into a globally callable capability.

Built on the EasyNet stack: identity, signed invocations, and receipts
come from easynet-daemon + Axon; this package is the Python facade
(SPEC: docs/design/easyremote-v2-easynet-refactor.md).

Exports grow as SPEC §5.1 modules land; everything exported here is
implemented and tested.
"""

from ._version import __version__
from .client import BidiSession, Client, RemoteFunction, Stream, remote
from .config import configure
from .context import Context
from .errors import (
    Cancelled,
    DeadlineExceeded,
    InternalError,
    InvalidArgument,
    PermissionDenied,
    RemoteError,
    ResourceExhausted,
    SchemaError,
    Unavailable,
)
from .gateway import Gateway, Server, TLSConfig
from .invocation import Invocation, InvocationTuple, PreparedInvocation
from .node import ComputeNode
from .pipeline import MissionRun, Pipeline
from .receipts import InvocationState, Receipt, ReceiptChain

__all__ = [
    "BidiSession",
    "Cancelled",
    "Client",
    "ComputeNode",
    "Context",
    "DeadlineExceeded",
    "Gateway",
    "InternalError",
    "InvalidArgument",
    "Invocation",
    "InvocationState",
    "InvocationTuple",
    "MissionRun",
    "PermissionDenied",
    "Pipeline",
    "PreparedInvocation",
    "Receipt",
    "ReceiptChain",
    "RemoteError",
    "RemoteFunction",
    "ResourceExhausted",
    "SchemaError",
    "Server",
    "Stream",
    "TLSConfig",
    "Unavailable",
    "__version__",
    "configure",
    "remote",
]
