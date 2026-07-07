"""Mission facade: direct EAL run/track/cancel over daemon Invocation."""

import pytest
from test_client import IDENTITY, FakeTransport, ok_response

from easyremote.client import Client
from easyremote.errors import InvalidArgument
from easyremote.mission import MissionControl


def make_client(responses=None):
    transport = FakeTransport(responses=responses)
    return Client(transport=transport, identity=IDENTITY), transport


def test_run_eal_uses_daemon_unary_system_ability():
    client, transport = make_client(
        responses=[ok_response({"ok": True, "run_id": "run-1", "outputs": {}})]
    )

    run = MissionControl(client).run_eal('mission "nightly" {}\n', label="nightly")

    assert run.run_id == "run-1"
    assert transport.carriers == ["unary"]
    wire = transport.invocations[0]
    assert (
        wire["descriptor_ref"]
        == "easynet:///r/acme/ability/device.dev-a.mission.run@1.0.0"
    )
    assert wire["args"] == {
        "source": 'mission "nightly" {}\n',
        "label": "nightly",
    }


def test_run_file_uses_file_stem_as_default_label(tmp_path):
    source = tmp_path / "cleanup.eal"
    source.write_text('mission "cleanup" {}\n')
    client, transport = make_client(responses=[ok_response({"run_id": "run-2"})])

    run = MissionControl(client).run_file(source)

    assert run.run_id == "run-2"
    assert transport.invocations[0]["args"]["label"] == "cleanup"
    assert transport.invocations[0]["args"]["source"] == 'mission "cleanup" {}\n'


def test_track_and_cancel_validate_run_id_and_use_unary():
    client, transport = make_client(
        responses=[
            ok_response({"state": "running"}),
            ok_response({"cancelled": True}),
        ]
    )
    control = MissionControl(client)

    assert control.track("run-9") == {"state": "running"}
    assert control.cancel("run-9") == {"cancelled": True}

    assert transport.carriers == ["unary", "unary"]
    assert transport.invocations[0]["args"] == {"run_id": "run-9"}
    assert transport.invocations[1]["descriptor_ref"].endswith(
        "/ability/device.dev-a.mission.cancel@1.0.0"
    )
    with pytest.raises(InvalidArgument) as exc_info:
        control.track(" ")
    assert exc_info.value.reason == "empty_run_id"


def test_events_fetches_mission_event_page():
    page_response = {
        "cursor_sequence": 4,
        "next_cursor_sequence": 5,
        "has_more": False,
        "dropped_count": 0,
        "events": [
            {
                "sequence": 4,
                "event_type": "completed",
                "occurred_unix_ms": 1_700_000_000_000,
                "terminal": True,
                "payload": {"ok": True},
                "receipt": {"receipt_ura": "easynet:///r/acme/resource/agent.easyremote.test/invocation/r-1/receipt"},
            }
        ],
    }
    client, transport = make_client(
        responses=[
            ok_response(page_response),
            ok_response({"run_id": "run-9"}),
            ok_response(page_response | {"next_cursor_sequence": 6}),
        ]
    )
    control = MissionControl(client)

    page = control.events("run-9", cursor_sequence=4, limit=50)
    handle_page = control.run_eal('mission "nightly" {}\n').events(cursor_sequence=5)

    assert page["next_cursor_sequence"] == 5
    assert page["events"][0]["event_type"] == "completed"
    assert handle_page["next_cursor_sequence"] == 6
    assert transport.invocations[0]["descriptor_ref"].endswith(
        "/ability/device.dev-a.mission.events@1.0.0"
    )
    assert transport.invocations[0]["args"] == {
        "run_id": "run-9",
        "cursor_sequence": 4,
        "limit": 50,
    }
    assert transport.invocations[1]["args"] == {
        "source": 'mission "nightly" {}\n',
    }
    assert transport.invocations[2]["args"] == {
        "run_id": "run-9",
        "cursor_sequence": 5,
    }


def test_invalid_eal_inputs_are_rejected():
    client, _ = make_client()
    control = MissionControl(client)

    with pytest.raises(InvalidArgument) as exc_info:
        control.run_eal(" ")
    assert exc_info.value.reason == "empty_eal_source"

    with pytest.raises(InvalidArgument) as exc_info:
        control.run_file("/definitely/missing.eal")
    assert exc_info.value.reason == "eal_file_unreadable"
