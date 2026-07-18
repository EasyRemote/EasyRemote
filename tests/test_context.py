"""Server-side Context child dispatch semantics."""

import easynet_sdk
import pytest

from easyremote._context_dispatch import dispatcher_from_parent_receipt
from easyremote.context import Context
from easyremote.errors import Unavailable
from easyremote.invocation_policy import ChildCausal
from easyremote.receipts import InvocationState


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


def test_context_child_dispatch_requires_parent_receipt_anchor():
    ctx = Context(invocation_id="inv-1", caller="easynet:///r/acme/user/alice")

    with pytest.raises(Unavailable) as exc_info:
        ctx.call("er.child", q="hi")

    assert exc_info.value.reason == "context_dispatch_not_wired"


def test_context_delegates_child_calls_and_closes_dispatcher():
    dispatcher = FakeChildDispatcher()
    ctx = Context(
        invocation_id="inv-1",
        caller="easynet:///r/acme/user/alice",
        _child_dispatcher=dispatcher,
    )

    assert ctx.call("er.child", "x", q="hi") == {
        "function": "er.child",
        "args": ("x",),
        "kwargs": {"q": "hi"},
    }
    assert ctx.invoke("er.child") == "invocation"
    assert list(ctx.stream("er.child")) == ["frame"]

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
            state=int(InvocationState.COMPLETED),
            receipt_ura="easynet:///r/example/resource/agent.easyremote.test/invocation/parent-1/receipt",
            cleanup_complete=True,
        )
    )

    dispatcher = dispatcher_from_parent_receipt(parent, client_factory=lambda: fake)
    assert dispatcher is not None
    assert dispatcher.call("er.child", q="hi") == "child-result"

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
            state=int(InvocationState.COMPLETED),
            cleanup_complete=True,
        )
    )

    with pytest.raises(Unavailable) as exc_info:
        dispatcher_from_parent_receipt(parent)

    assert exc_info.value.reason == "parent_receipt_anchor_unavailable"
