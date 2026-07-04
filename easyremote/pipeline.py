"""Pipeline → EAL → ``mission.run`` (SPEC §5.9; grammar-verified).

EAL's dependency edges are **dataflow only**: a later step references
an earlier one as ``alias.output``, and the daemon's planner derives
the phase DAG from those references (eal-grammar.md — there is no
standalone "after" syntax, which is why this API has no ``after=``
parameter: ordering *is* data).

Grammar limits honored at build time, not at run time:

- field values are scalars (string/int/float/bool) or step refs —
  nested objects/lists are rejected with guidance;
- failure policies are ``abort | skip | retry | continue``.

The facade compiles; the daemon executes (``mission.run`` →
``{ok, run_id, run_dir, outputs, meta}``, ``mission.track`` /
``mission.cancel`` take ``{run_id}``). No second orchestration
runtime lives here.

Provenance: the generated source carries a ``created_by`` comment
header when the client identity is available; the *structured*
provenance contract for EAL artifacts is a flagged P0 item.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeAlias

import easynet_sdk

from ._version import __version__
from .errors import InvalidArgument
from .mission import MissionControl, MissionRun
from .node import RegisteredFunction

if TYPE_CHECKING:
    from .client import Client

__all__ = ["MissionRun", "Pipeline", "Step", "StepOutput"]

StepOutput: TypeAlias = easynet_sdk.EasyRemotePipelineStepOutput
Step: TypeAlias = easynet_sdk.EasyRemotePipelineStep


@dataclass
class Pipeline:
    """A mission under construction.

    Cycles are impossible by construction: a step can only reference
    the outputs of steps that already exist.
    """

    name: str
    client: Client | None = None
    _plan: easynet_sdk.EasyRemotePipelinePlan = field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            self._plan = easynet_sdk.EasyRemotePipelinePlan(
                self.name,
                created_by=self._created_by(),
                version=__version__,
            )
        except easynet_sdk.SDKError as exc:
            raise _pipeline_error(exc) from exc

    def step(
        self,
        target: str | RegisteredFunction,
        *,
        on: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        on_failure: str | None = None,
        optional: bool = False,
        **args: Any,
    ) -> Step:
        """Append one call; pass upstream results as ``other.output``."""
        ref = self._target_ref(target)
        try:
            return self._plan.step(
                ref,
                on=on,
                timeout=timeout,
                retries=retries,
                on_failure=on_failure,
                optional=optional,
                args=args,
            )
        except easynet_sdk.SDKError as exc:
            raise _pipeline_error(exc) from exc

    def to_eal(self) -> str:
        """The mission source — inspectable before anything runs."""
        try:
            return self._plan.to_eal()
        except easynet_sdk.SDKError as exc:
            raise _pipeline_error(exc) from exc

    def run(self, *, label: str | None = None) -> MissionRun:
        return MissionControl(self.client).run_eal(
            self.to_eal(),
            label=label or self.name,
        )

    def child_invocation_intents(
        self,
    ) -> tuple[easynet_sdk.EasyRemotePipelineChildInvocationIntent, ...]:
        return self._plan.child_invocation_intents()

    def validate_child_invocations(
        self, status: easynet_sdk.MissionStatus
    ) -> easynet_sdk.EasyRemotePipelineChildInvocationConformance:
        try:
            return self._plan.validate_child_invocations(status)
        except easynet_sdk.SDKError as exc:
            raise _pipeline_error(exc) from exc

    # -- internals -----------------------------------------------------------

    def _target_ref(self, target: str | RegisteredFunction) -> str:
        if isinstance(target, RegisteredFunction):
            return target.qualified_name
        if isinstance(target, str) and target.strip():
            return target.strip()
        raise InvalidArgument(
            "step target must be a qualified ability name (str) or a"
            f" RegisteredFunction, got {type(target).__name__}",
            reason="invalid_step_target",
        )

    def _created_by(self) -> str:
        if self.client is None:
            return ""
        try:
            return self.client._who().device_ura
        except Exception:  # identity not paired yet — header is optional
            return ""


def _pipeline_error(error: easynet_sdk.SDKError) -> InvalidArgument:
    reason = error.details.get("reason")
    message = error.message or str(error)
    return InvalidArgument(
        message,
        reason=(
            str(reason)
            if isinstance(reason, str)
            else _pipeline_reason(message)
        ),
    )


def _pipeline_reason(message: str) -> str:
    if "pipeline name" in message and "empty" in message:
        return "empty_name"
    if "has no steps" in message:
        return "empty_pipeline"
    if "on_failure" in message:
        return "invalid_failure_policy"
    if "timeout" in message:
        return "invalid_timeout"
    if "retries" in message:
        return "invalid_retries"
    if "non-finite" in message or "EAL number must be finite" in message:
        return "non_finite_field"
    if "not part of this pipeline" in message:
        return "foreign_step_output"
    if "EAL field values are scalars" in message:
        return "non_scalar_field"
    return "sdk_pipeline_invalid_argument"
