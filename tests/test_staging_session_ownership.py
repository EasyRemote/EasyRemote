"""Package transfer keeps its owner when a concurrent unary wait retires."""

import threading

import pytest
from test_control import IDENTITY, FakeTransport, _FakeBidiSession, ok_response

from easyremote._sdk_transport import Transport
from easyremote.client import Client
from easyremote.control import AbilityControl
from easyremote.errors import DeadlineExceeded, Unavailable


def test_install_survives_unary_retirement_during_transfer_open(tmp_path, monkeypatch):
    opened = threading.Event()
    finish_open = threading.Event()
    finish_unary = threading.Event()
    retired = threading.Event()

    class OwnedSession(_FakeBidiSession):
        def __init__(self, owner):
            super().__init__()
            self.owner = owner

        def send(self, frame):
            assert not self.owner.closed, "staging used a retired unary owner"
            return super().send(frame)

    class OwnedTransport(FakeTransport):
        def __init__(self, *, retiring=False, responses=()):
            super().__init__(responses)
            self.retiring = retiring
            self.closed = False
            self.close_count = 0

        def invoke(self, draft):
            if self.retiring:
                assert finish_unary.wait(3)
                return {}
            return super().invoke(draft)

        def open_runtime_ability_bidi(self, *args):
            super().open_runtime_ability_bidi(*args)
            session = OwnedSession(self)
            self.bidi_invocations[-1]["session"] = session
            opened.set()
            assert finish_open.wait(3)
            return session

        def close(self):
            self.closed = True
            self.close_count += 1
            super().close()
            if self.retiring:
                retired.set()

    unary = OwnedTransport(retiring=True)
    streaming = OwnedTransport()
    replacement = OwnedTransport(responses=[ok_response({
        "install_id": "inst-1",
        "ability_ura": "easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.fn",
        "state": "ACTIVE",
    })])
    connections = iter([unary, streaming, replacement])
    monkeypatch.setattr(
        Transport, "connect", classmethod(lambda cls: next(connections))
    )
    client = Client(identity=IDENTITY)
    assert client._connected() is unary
    package = tmp_path / "package"
    package.mkdir()
    (package / "ability.json").write_text("{}")
    results, failures = [], []

    def install():
        try:
            results.append(AbilityControl(client).install(package))
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=install)
    worker.start()
    try:
        assert opened.wait(2)
        with pytest.raises(DeadlineExceeded):
            client._unary_pool.invoke({}, timeout=0.01)
        finish_unary.set()
        assert retired.wait(2)
        assert not streaming.closed
    finally:
        finish_unary.set()
        finish_open.set()
        worker.join(3)
        client.close()
        client.close()
    assert not worker.is_alive()
    assert failures == []
    assert results[0].install_id == "inst-1"
    assert unary.bidi_invocations == []
    transfer = streaming.bidi_invocations[0]
    assert transfer["ability_name"] == "fs.transfer"
    assert [frame.kind for frame in transfer["session"].sent] == ["binary_chunk", "eof"]
    assert transfer["session"].closed
    assert unary.close_count == streaming.close_count == replacement.close_count == 1


def test_client_close_cannot_leave_a_late_created_stream_owner(monkeypatch):
    connecting = threading.Event()
    finish_connect = threading.Event()

    class Owner:
        close_count = 0

        def close(self):
            self.close_count += 1

    owner = Owner()

    def connect(cls):
        connecting.set()
        assert finish_connect.wait(3)
        return owner

    monkeypatch.setattr(Transport, "connect", classmethod(connect))
    client = Client(identity=IDENTITY)
    returned = []
    errors = []

    def create():
        try:
            returned.append(client._streaming())
        except BaseException as exc:
            errors.append(exc)

    creator = threading.Thread(target=create)
    closer = threading.Thread(target=client.close)
    creator.start()
    try:
        assert connecting.wait(2)
        closer.start()
    finally:
        finish_connect.set()
        creator.join(3)
        closer.join(3)
    assert not creator.is_alive() and not closer.is_alive()
    assert errors == []
    assert returned == [owner]
    assert owner.close_count == 1
    with pytest.raises(Unavailable, match="Client is closed"):
        client._streaming()
    client.close()
    assert owner.close_count == 1


def test_close_before_first_stream_does_not_connect(monkeypatch):
    def forbidden(cls):
        raise AssertionError("closed Client must not create a transport")

    monkeypatch.setattr(Transport, "connect", classmethod(forbidden))
    client = Client(identity=IDENTITY)
    client.close()
    with pytest.raises(Unavailable, match="Client is closed"):
        client._streaming()
