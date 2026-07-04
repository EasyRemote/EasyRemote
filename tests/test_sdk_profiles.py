"""EasyRemote delegates Admin/Mission profile glue to EasyNet-Cli SDK."""

from __future__ import annotations

from dataclasses import dataclass

import easynet_sdk
import pytest

from easyremote._sdk_profiles import admin_facade, mission_facade


def test_admin_facade_dispatches_through_sdk_profile_bridge() -> None:
    client = FakeClient()

    started = admin_facade(client).start_agent(
        "assistant",
        kind="codex",
        model="gpt-5",
        command="codex",
        args=("run",),
    )
    records = admin_facade(client).list_agents()

    assert started.name == "assistant"
    assert started.runtime == "codex"
    assert started.model == "gpt-5"
    assert records[0].name == "assistant"
    assert client.calls[0] == (
        "agent.start",
        {
            "name": "assistant",
            "agent_type": "codex",
            "model": "gpt-5",
            "model_present": True,
            "label": None,
            "command": "codex",
            "command_args": ["run"],
            "materialize_directory": True,
            "update_existing_spec": False,
            "project_workspace": True,
        },
    )
    assert client.calls[1] == ("agent.list", {})


def test_mission_facade_dispatches_through_sdk_profile_bridge() -> None:
    client = FakeClient()
    mission = mission_facade(client)

    run = mission.run_eal('mission "weather" {}\n', label="weather")
    tracked = mission.track("run-1")
    events = mission.events("run-1", cursor_sequence=4, limit=25)

    assert run.run_id == "run-1"
    assert run.run_dir == "/tmp/run-1"
    assert run.outputs == {"report": "ok"}
    assert tracked["state"] == "completed"
    assert events["next_cursor_sequence"] == 5
    assert client.calls == [
        ("mission.run", {"source": 'mission "weather" {}\n', "label": "weather"}),
        ("mission.track", {"run_id": "run-1"}),
        ("mission.events", {"run_id": "run-1", "cursor_sequence": 4, "limit": 25}),
    ]


def test_profile_bridge_rejects_missing_device_identity() -> None:
    client = FakeClient(device_ura="")

    with pytest.raises(easynet_sdk.SDKError) as exc_info:
        admin_facade(client).list_agents()

    assert exc_info.value.code is easynet_sdk.ErrorCode.INVALID_ARGUMENT
    assert exc_info.value.stage == "easyremote_profile"


@dataclass(frozen=True)
class FakeIdentity:
    device_ura: str


class FakeInvocation:
    def __init__(self, result: dict[str, object]) -> None:
        self._result = result

    def result(self) -> dict[str, object]:
        return dict(self._result)


class FakeClient:
    def __init__(self, *, device_ura: str = "easynet:///r/acme/device/dev-a") -> None:
        self._identity = FakeIdentity(device_ura)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def _who(self) -> FakeIdentity:
        return self._identity

    def invoke(self, ability: str, **kwargs: object) -> FakeInvocation:
        self.calls.append((ability, dict(kwargs)))
        if ability == "agent.start":
            return FakeInvocation(
                {
                    "state": "ok",
                    "model": kwargs.get("model"),
                    "root_path": "/tmp/assistant",
                    "replaced_prior": False,
                }
            )
        if ability == "agent.list":
            return FakeInvocation(
                {
                    "agents": [
                        {
                            "name": "assistant",
                            "runtime": "codex",
                            "model": "gpt-5",
                            "metadata": {"root_path": "/tmp/assistant"},
                        }
                    ]
                }
            )
        if ability == "mission.run":
            return FakeInvocation(
                {
                    "run_id": "run-1",
                    "run_dir": "/tmp/run-1",
                    "outputs": {"report": "ok"},
                    "state": "running",
                }
            )
        if ability == "mission.track":
            return FakeInvocation(
                {
                    "run_id": "run-1",
                    "run_dir": "/tmp/run-1",
                    "outputs": {"report": "ok"},
                    "state": "completed",
                    "terminal": True,
                }
            )
        if ability == "mission.events":
            return FakeInvocation(
                {
                    "cursor_sequence": kwargs["cursor_sequence"],
                    "next_cursor_sequence": 5,
                    "has_more": False,
                    "dropped_count": 0,
                    "events": [
                        {
                            "sequence": 4,
                            "event_type": "progress",
                            "occurred_unix_ms": 1783126923000,
                            "terminal": False,
                            "payload": {"step": "s1"},
                            "receipt": {},
                            "metadata": {"source": "test"},
                        }
                    ],
                }
            )
        raise AssertionError(f"unexpected ability {ability}")
