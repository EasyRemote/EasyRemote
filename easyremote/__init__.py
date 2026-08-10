"""EasyRemote — turn a local function into a globally callable capability.

Built on the EasyNet stack: identity, signed invocations, and receipts
come from easynet-daemon + Axon; this package is the Python facade
(SPEC: docs/design/easyremote-v2-easynet-refactor.md).

Exports grow as SPEC §5.1 modules land; everything exported here is
implemented and tested.
"""

from ._version import __version__
from .agent import AgentChatResult, RemoteAgent, agent
from .client import (
    BidiSession,
    CallTarget,
    Client,
    RemoteAbility,
    RemoteDevice,
    RemoteFunction,
    RemoteOwner,
    Stream,
    remote,
)
from .config import configure
from .context import Context, ContextTarget
from .control import (
    AbilityControl,
    AbilityInstallResult,
    AbilityRecord,
    AgentControl,
    AgentRecord,
    AgentStartResult,
    AgentStopResult,
)
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
from .invocation import Invocation, PreparedInvocation
from .invocation_policy import (
    ChildCausal,
    CompleteExplicit,
    ExplicitSubject,
    FreshCausal,
    FreshContextChild,
    FreshRoot,
    InvocationDerivationPolicy,
    InvocationSubjectPolicy,
    ResolvedTargetSubject,
)
from .mission import MissionControl
from .node import ComputeNode
from .pipeline import MissionRun, Pipeline

__all__ = [
    "AbilityControl",
    "AbilityInstallResult",
    "AbilityRecord",
    "AgentChatResult",
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
    "ContextTarget",
    "DeadlineExceeded",
    "ExplicitSubject",
    "FreshCausal",
    "FreshContextChild",
    "FreshRoot",
    "InternalError",
    "InvalidArgument",
    "Invocation",
    "InvocationDerivationPolicy",
    "InvocationSubjectPolicy",
    "MissionControl",
    "MissionRun",
    "PermissionDenied",
    "Pipeline",
    "PreparedInvocation",
    "RemoteAbility",
    "RemoteAgent",
    "RemoteDevice",
    "RemoteError",
    "RemoteFunction",
    "RemoteOwner",
    "ResolvedTargetSubject",
    "ResourceExhausted",
    "SchemaError",
    "Stream",
    "Unavailable",
    "__version__",
    "agent",
    "configure",
    "remote",
]
