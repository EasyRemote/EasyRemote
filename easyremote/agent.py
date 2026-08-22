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
    session_id: str
    request_id: str
    invocation_ura: str
    trace_id: str
    status: str
    elapsed_ms: int | None
    usage: Mapping[str, object]
    skills_loaded: tuple[str, ...]
    context_used: tuple[Mapping[str, object], ...]
    tool_calls: tuple[Mapping[str, object], ...]
    timeline: tuple[Mapping[str, object], ...]
    trace: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "prediction": self.prediction,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "invocation_ura": self.invocation_ura,
            "trace_id": self.trace_id,
            "status": self.status,
            "elapsed_ms": self.elapsed_ms,
            "usage": dict(self.usage),
            "skills_loaded": list(self.skills_loaded),
            "context_used": [dict(item) for item in self.context_used],
            "tool_calls": [dict(item) for item in self.tool_calls],
            "timeline": [dict(item) for item in self.timeline],
            "trace": dict(self.trace),
        }


@dataclass(frozen=True)
class _TraceIdentity:
    request_id: str
    invocation_ura: str
    trace_id: str
    status: str
    trace: Mapping[str, object]


class RemoteAgent(RemoteOwner):
    """An agent owner with a strict, structured single-turn chat operation."""

    def __init__(
        self,
        client: Client,
        owner_ura: str,
        agent_name: str,
        *,
        resolve_owner: bool = False,
    ) -> None:
        super().__init__(client, owner_ura)
        self._agent_name = agent_name
        self._resolve_owner = resolve_owner

    @property
    def name(self) -> str:
        return self._agent_name

    def _target(self, function: str) -> CallTarget:
        return CallTarget(function=function, owner_ura=self._resolved_owner_ura())

    def chat(
        self,
        *,
        messages: Sequence[Mapping[str, object]],
        subject: str,
        execution: Mapping[str, object],
        driver: Mapping[str, object] | None = None,
    ) -> AgentChatResult:
        normalized_messages = _messages(messages)
        normalized_execution, timeout_seconds = _execution(execution)
        normalized_driver = _driver(driver)
        external_subject = _required_text(subject, "subject")
        canonical_subject = _subject_ura(self._client, external_subject)
        owner_ura = self._resolved_owner_ura()
        chat_ability_ura = self._client._addressing.owner_ability_ura(
            owner_ura,
            "chat",
        )
        target = CallTarget(
            function=chat_ability_ura,
            owner_ura=owner_ura,
            timeout=timeout_seconds + _CLIENT_TIMEOUT_MARGIN_SECONDS,
            metadata={
                "easyremote.external_subject": external_subject,
                "easyremote.profile": "agent.chat.strict.v1",
            },
            invocation_policy=FreshRoot(ExplicitSubject(canonical_subject)),
        )
        try:
            args: dict[str, object] = {
                "messages": normalized_messages,
                "execution": normalized_execution,
            }
            if normalized_driver:
                args["driver"] = normalized_driver
            invocation = self._client.invoke(
                target,
                **args,
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
        elapsed_ms = _optional_non_negative_int(response.get("elapsed_ms"))
        session_id = response.get("session_id")
        if not isinstance(session_id, str):
            session_id = ""
        skills_loaded = _string_array(response.get("skills_loaded"), "skills_loaded")
        context_used = _object_array(response.get("context_used"), "context_used")
        raw_tool_calls = _object_array(response.get("tool_calls"), "tool_calls")
        raw_timeline = _object_array(response.get("timeline"), "timeline")
        trace_identity = _trace_identity(self._client, invocation, request_id)
        return AgentChatResult(
            prediction=prediction,
            session_id=session_id,
            request_id=trace_identity.request_id,
            invocation_ura=trace_identity.invocation_ura,
            trace_id=trace_identity.trace_id,
            status=trace_identity.status,
            elapsed_ms=elapsed_ms,
            usage=dict(usage),
            skills_loaded=tuple(skills_loaded),
            context_used=tuple(dict(item) for item in context_used),
            tool_calls=tuple(dict(item) for item in raw_tool_calls),
            timeline=tuple(dict(item) for item in raw_timeline),
            trace=trace_identity.trace,
        )

    def _resolved_owner_ura(self) -> str:
        if not self._resolve_owner:
            return self.owner_ura
        return self._client._agent_call_owner_ura(self._agent_name)


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


def _trace_identity(
    client: Client,
    invocation: object,
    request_id: str,
) -> _TraceIdentity:
    try:
        graph = client._invocation_trace(request_id)
    except RemoteError as trace_error:
        receipt = getattr(invocation, "receipt", None)
        receipt_ura = str(getattr(receipt, "receipt_ura", "") or "")
        return _TraceIdentity(
            request_id=request_id,
            invocation_ura=receipt_ura,
            trace_id="",
            status=_invocation_status(invocation),
            trace={
                "trace_lookup_error": (
                    f"{type(trace_error).__name__}: {trace_error}"
                ),
                "records": [],
                "edges": [],
            },
        )
    record = next(
        (item for item in graph.records if item.request_id == request_id),
        None,
    )
    if record is None:
        raise InternalError(
            f"native trace has no record for request {request_id}",
            reason="trace_record_missing",
        )
    return _TraceIdentity(
        request_id=record.request_id,
        invocation_ura=record.invocation_ura,
        trace_id=record.trace_id,
        status=record.state,
        trace=graph.to_dict(),
    )


def _invocation_status(invocation: object) -> str:
    state = getattr(invocation, "state", None)
    name = str(getattr(state, "name", "") or "")
    return name.lower() if name else ""


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


def _driver(driver: Mapping[str, object] | None) -> dict[str, object]:
    if driver is None:
        return {}
    if not isinstance(driver, Mapping):
        raise InvalidArgument(
            "driver must be an object",
            reason="invalid_agent_driver",
        )
    unknown = set(driver) - {"model"}
    if unknown:
        raise InvalidArgument(
            f"driver has unsupported fields: {sorted(unknown)}",
            reason="invalid_agent_driver",
        )
    raw_model = driver.get("model")
    if raw_model is None:
        return {}
    if not isinstance(raw_model, str) or not raw_model.strip():
        raise InvalidArgument(
            "driver.model must be a non-empty string",
            reason="invalid_agent_driver_model",
        )
    return {"model": raw_model.strip()}


def _object_array(value: object, field: str) -> list[Mapping[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise InternalError(
            f"Agent chat result field '{field}' must be an object array",
            reason="invalid_agent_response",
        )
    return value


def _string_array(value: object, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InternalError(
            f"Agent chat result field '{field}' must be a string array",
            reason="invalid_agent_response",
        )
    return value


def _optional_non_negative_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0:
        return int(value)
    return None


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
