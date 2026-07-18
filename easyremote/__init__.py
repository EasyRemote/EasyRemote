"""EasyRemote — turn a local function into a globally callable capability.

Built on the EasyNet stack: identity, signed invocations, and receipts
come from easynet-daemon + Axon; this package is the Python facade
(SPEC: docs/design/easyremote-v2-easynet-refactor.md).

Exports grow as SPEC §5.1 modules land; everything exported here is
implemented and tested.
"""

from ._version import __version__
from .bootstrap import DeviceRuntimeBootstrap, RuntimeBootstrapState
from .client import (
    BidiSession,
    CallTarget,
    Client,
    RemoteFunction,
    RemoteOwner,
    Stream,
    remote,
)
from .config import configure
from .context import Context
from .control import (
    AbilityControl,
    AbilityInstallResult,
    AbilityRecord,
    AgentControl,
    AgentRecord,
    AgentStartResult,
    AgentStopResult,
)
from .daemon import DaemonHandle, DaemonStartConfig
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
from .invocation_policy import (
    DEFAULT_INVOCATION_POLICY,
    ChildCausal,
    CompleteExplicit,
    ExplicitSubject,
    FreshCausal,
    FreshRoot,
    InvocationDerivationPolicy,
    InvocationSubjectPolicy,
    ResolvedTargetSubject,
)
from .mission import MissionControl
from .node import ComputeNode
from .pipeline import MissionRun, Pipeline
from .receipts import InvocationState, Receipt, ReceiptChain

__all__ = [
    "DEFAULT_INVOCATION_POLICY",
    "AbilityControl",
    "AbilityInstallResult",
    "AbilityRecord",
    "AgentControl",
    "AgentRecord",
    "AgentStartResult",
    "AgentStopResult",
    "BidiSession",
    "CallTarget",
    "Cancelled",
    "ChildCausal",
    "Client",
    "CompleteExplicit",
    "ComputeNode",
    "Context",
    "DaemonHandle",
    "DaemonStartConfig",
    "DeadlineExceeded",
    "DeviceRuntimeBootstrap",
    "ExplicitSubject",
    "FreshCausal",
    "FreshRoot",
    "Gateway",
    "InternalError",
    "InvalidArgument",
    "Invocation",
    "InvocationDerivationPolicy",
    "InvocationState",
    "InvocationSubjectPolicy",
    "InvocationTuple",
    "MissionControl",
    "MissionRun",
    "PermissionDenied",
    "Pipeline",
    "PreparedInvocation",
    "Receipt",
    "ReceiptChain",
    "RemoteError",
    "RemoteFunction",
    "RemoteOwner",
    "ResolvedTargetSubject",
    "ResourceExhausted",
    "RuntimeBootstrapState",
    "SchemaError",
    "Server",
    "Stream",
    "TLSConfig",
    "Unavailable",
    "__version__",
    "configure",
    "remote",
]
