"""Structured Agent-as-a-function facade over canonical EasyNet Invocation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath

from .client import CallTarget, Client, RemoteOwner
from .errors import InternalError, InvalidArgument, RemoteError
from .identity import resource_ura
from .invocation_policy import ExplicitSubject, FreshRoot

__all__ = ["AgentChatResult", "RemoteAgent", "agent"]

MAX_AGENT_TIMEOUT_MS = 900_000
_CLIENT_TIMEOUT_MARGIN_SECONDS = 30.0


@dataclass(frozen=True)
class AgentChatResult:
    """One successful Agent chat result joined to its native Axon trace."""

    prediction: str
    request_id: str
    invocation_ura: str
    trace_id: str
    status: str
    usage: Mapping[str, object]
    tool_calls: tuple[Mapping[str, object], ...]
    trace: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "prediction": self.prediction,
            "request_id": self.request_id,
            "invocation_ura": self.invocation_ura,
            "trace_id": self.trace_id,
            "status": self.status,
            "usage": dict(self.usage),
            "tool_calls": [dict(item) for item in self.tool_calls],
            "trace": dict(self.trace),
        }


class RemoteAgent(RemoteOwner):
    """An agent owner with a strict, structured single-turn chat operation."""

    def __init__(self, client: Client, owner_ura: str, agent_name: str) -> None:
        super().__init__(client, owner_ura)
        self._agent_name = agent_name

    @property
    def name(self) -> str:
        return self._agent_name

    def chat(
        self,
        *,
        messages: Sequence[Mapping[str, object]],
        subject: str,
        execution: Mapping[str, object],
    ) -> AgentChatResult:
        normalized_messages = _messages(messages)
        normalized_execution, timeout_seconds = _execution(execution)
        external_subject = _required_text(subject, "subject")
        canonical_subject = _subject_ura(self._client, external_subject)
        target = CallTarget(
            function=f"{self._agent_name}.chat",
            owner_ura=self.owner_ura,
            timeout=timeout_seconds + _CLIENT_TIMEOUT_MARGIN_SECONDS,
            metadata={
                "easyremote.external_subject": external_subject,
                "easyremote.profile": "agent.chat.strict.v1",
            },
            invocation_policy=FreshRoot(ExplicitSubject(canonical_subject)),
        )
        try:
            invocation = self._client.invoke(
                target,
                messages=normalized_messages,
                execution=normalized_execution,
            )
        except RemoteError as error:
            _attach_failure_trace(self._client, error)
            raise
        request_id = invocation.id.strip()
        if not request_id:
            raise InternalError(
                "Agent invocation completed without a canonical request id",
                reason="missing_invocation_identity",
            )
        graph = self._client._invocation_trace(request_id)
        record = next(
            (item for item in graph.records if item.request_id == request_id),
            None,
        )
        if record is None:
            raise InternalError(
                f"native trace has no record for request {request_id}",
                reason="trace_record_missing",
            )
        response = invocation.result()
        if not isinstance(response, Mapping):
            raise InternalError(
                "Agent chat result must be an object",
                reason="invalid_agent_response",
            )
        prediction = response.get("reply")
        if not isinstance(prediction, str):
            raise InternalError(
                "Agent chat result is missing string field 'reply'",
                reason="invalid_agent_response",
            )
        usage = response.get("usage")
        if not isinstance(usage, Mapping):
            usage = {}
        raw_tool_calls = response.get("tool_calls")
        if not isinstance(raw_tool_calls, list) or not all(
            isinstance(item, Mapping) for item in raw_tool_calls
        ):
            raise InternalError(
                "Agent chat result field 'tool_calls' must be an object array",
                reason="invalid_agent_response",
            )
        return AgentChatResult(
            prediction=prediction,
            request_id=record.request_id,
            invocation_ura=record.invocation_ura,
            trace_id=record.trace_id,
            status=record.state,
            usage=dict(usage),
            tool_calls=tuple(dict(item) for item in raw_tool_calls),
            trace=graph.to_dict(),
        )


def agent(spec: str, *, client: Client | None = None) -> RemoteAgent:
    """Return a local-user Agent handle for ``easyremote.agent(...).chat``."""

    return (client or Client()).agent(spec)


def _attach_failure_trace(client: Client, error: RemoteError) -> None:
    request_id = (error.invocation_id or "").strip()
    if not request_id:
        return
    try:
        graph = client._invocation_trace(request_id)
        if not any(record.request_id == request_id for record in graph.records):
            raise ValueError(f"native trace has no record for request {request_id}")
        error.trace = graph.to_dict()
    except Exception as trace_error:
        error.trace_lookup_error = f"{type(trace_error).__name__}: {trace_error}"


def _messages(
    messages: Sequence[Mapping[str, object]],
) -> list[dict[str, str]]:
    if isinstance(messages, (str, bytes)):
        raise InvalidArgument(
            "messages must be an array",
            reason="invalid_agent_messages",
        )
    normalized: list[dict[str, str]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, Mapping) or set(message) != {"role", "content"}:
            raise InvalidArgument(
                f"messages[{index}] must contain exactly role and content",
                reason="invalid_agent_messages",
            )
        role = message.get("role")
        content = message.get("content")
        if (
            role not in {"system", "user"}
            or not isinstance(content, str)
            or not content
        ):
            raise InvalidArgument(
                f"messages[{index}] has an unsupported role or empty content",
                reason="invalid_agent_messages",
            )
        normalized.append({"role": str(role), "content": content})
    roles = [message["role"] for message in normalized]
    if roles not in (["user"], ["system", "user"]):
        raise InvalidArgument(
            "messages must be [user] or [system, user]",
            reason="unsupported_agent_conversation_shape",
        )
    return normalized


def _execution(execution: Mapping[str, object]) -> tuple[dict[str, object], float]:
    if not isinstance(execution, Mapping):
        raise InvalidArgument(
            "execution must be an object",
            reason="invalid_agent_execution",
        )
    unknown = set(execution) - {"cwd", "timeout_ms", "isolation"}
    if unknown:
        raise InvalidArgument(
            f"execution has unsupported fields: {sorted(unknown)}",
            reason="invalid_agent_execution",
        )
    raw_cwd = execution.get("cwd")
    if not isinstance(raw_cwd, (str, Path)):
        raise InvalidArgument(
            "execution.cwd must be an agent-root-relative path",
            reason="invalid_agent_execution_cwd",
        )
    cwd = str(raw_cwd)
    path = PurePath(cwd)
    if (
        not cwd
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise InvalidArgument(
            "execution.cwd must be a non-empty agent-root-relative descendant path",
            reason="invalid_agent_execution_cwd",
        )
    timeout_ms = execution.get("timeout_ms")
    if (
        isinstance(timeout_ms, bool)
        or not isinstance(timeout_ms, int)
        or timeout_ms <= 0
        or timeout_ms > MAX_AGENT_TIMEOUT_MS
    ):
        raise InvalidArgument(
            f"execution.timeout_ms must be between 1 and {MAX_AGENT_TIMEOUT_MS}",
            reason="invalid_agent_execution_timeout",
        )
    isolation = execution.get("isolation", "strict")
    if isolation != "strict":
        raise InvalidArgument(
            "structured Agent chat requires execution.isolation='strict'",
            reason="invalid_agent_execution_isolation",
        )
    return (
        {"cwd": cwd, "timeout_ms": timeout_ms, "isolation": "strict"},
        timeout_ms / 1000.0,
    )


def _subject_ura(client: Client, external_subject: str) -> str:
    identity = client._who()
    digest = hashlib.sha256(external_subject.encode("utf-8")).hexdigest()
    return resource_ura(
        identity.realm,
        f"device.{identity.node_id}",
        f"benchmark/invocation-subject/{digest}",
    )


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidArgument(
            f"{field} must be a non-empty string",
            reason=f"invalid_agent_{field}",
        )
    return value.strip()
