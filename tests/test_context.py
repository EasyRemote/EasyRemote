"""Server-side Context child dispatch semantics."""

import easynet_sdk
import pytest
from easynet_sdk import InvocationLifecycleState as InvocationState

from easyremote._context_dispatch import dispatcher_from_parent_receipt
from easyremote.context import Context, ContextTarget
from easyremote.errors import InvalidArgument, Unavailable
from easyremote.invocation_policy import (
    ChildCausal,
    FreshContextChild,
    ResolvedTargetSubject,
)


class FakeChildDispatcher:
    def __init__(self):
        self.calls = []
        self.closed = False

    def call(self, function, /, *args, **kwargs):
        self.calls.append(("call", function, args, kwargs))
        return {"function": function, "args": args, "kwargs": kwargs}

    def invoke(self, function, /, *args, **kwargs):
        self.calls.append(("invoke", function, args, kwargs))
        return "invocation"

    def stream(self, function, /, *args, **kwargs):
        self.calls.append(("stream", function, args, kwargs))
        return iter(["frame"])

    def close(self):
        self.closed = True


def child_target() -> ContextTarget:
    return Context.target(
        "er.child",
        invocation_policy=FreshContextChild(ResolvedTargetSubject()),
    )


def test_context_string_ingress_fails_closed_before_dispatcher_resolution():
    ctx = Context(invocation_id="inv-1", caller="easynet:///r/acme/user/alice")

    with pytest.raises(InvalidArgument) as exc_info:
        ctx.call("er.child", q="hi")  # type: ignore[arg-type]

    assert exc_info.value.reason == "missing_invocation_derivation_policy"


def test_context_child_dispatch_requires_parent_receipt_anchor():
    ctx = Context(invocation_id="inv-1", caller="easynet:///r/acme/user/alice")

    with pytest.raises(Unavailable) as exc_info:
        ctx.call(child_target(), q="hi")

    assert exc_info.value.reason == "context_dispatch_not_wired"


def test_context_delegates_child_calls_and_closes_dispatcher():
    dispatcher = FakeChildDispatcher()
    ctx = Context(
        invocation_id="inv-1",
        caller="easynet:///r/acme/user/alice",
        _child_dispatcher=dispatcher,
    )

    target = child_target()
    assert ctx.call(target, "x", q="hi") == {
        "function": target,
        "args": ("x",),
        "kwargs": {"q": "hi"},
    }
    assert ctx.invoke(target) == "invocation"
    assert list(ctx.stream(target)) == ["frame"]

    ctx.close()
    assert dispatcher.closed


class FakeClient:
    def __init__(self):
        self.seen = []
        self.closed = False

    def call(self, target, /, *args, **kwargs):
        self.seen.append(("call", target, args, kwargs))
        return "child-result"

    def invoke(self, target, /, *args, **kwargs):
        self.seen.append(("invoke", target, args, kwargs))
        return "child-invocation"

    def stream(self, target, /, *args, **kwargs):
        self.seen.append(("stream", target, args, kwargs))
        return iter(["child-frame"])

    def close(self):
        self.closed = True


def test_sdk_dispatcher_projects_parent_receipt_into_child_causal_ref(
    runtime_receipt,
):
    fake = FakeClient()
    parent = easynet_sdk.RuntimeReceipt.from_required_mapping(
        runtime_receipt(
            invocation_id="inv-parent-1",
            receipt_type="completed",
            state=InvocationState.COMPLETED.name,
            receipt_ura="easynet:///r/example/resource/agent.easyremote.test/invocation/parent-1/receipt",
            cleanup_complete=True,
        )
    )

    dispatcher = dispatcher_from_parent_receipt(parent, client_factory=lambda: fake)
    assert dispatcher is not None
    assert dispatcher.call(child_target(), q="hi") == "child-result"

    _, target, args, kwargs = fake.seen[0]
    assert target.function == "er.child"
    policy = target.invocation_policy
    assert isinstance(policy, ChildCausal)
    assert (
        policy.parent.receipt_ura
        == "easynet:///r/example/resource/agent.easyremote.test/invocation/parent-1/receipt"
    )
    assert policy.parent.receipt_hash == b"\xaa" * 32
    assert args == ()
    assert kwargs == {"q": "hi"}

    dispatcher.close()
    assert fake.closed


def test_sdk_dispatcher_rejects_parent_receipt_without_anchor(runtime_receipt):
    parent = easynet_sdk.RuntimeReceipt.from_required_mapping(
        runtime_receipt(
            invocation_id="inv-parent-1",
            receipt_type="completed",
            state=InvocationState.COMPLETED.name,
            cleanup_complete=True,
        )
    )

    with pytest.raises(Unavailable) as exc_info:
        dispatcher_from_parent_receipt(parent)

    assert exc_info.value.reason == "parent_receipt_anchor_unavailable"
