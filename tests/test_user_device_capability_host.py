#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for user-device capability host dynamic installation flow.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

import pytest

from easyremote.device_host import UserDeviceCapabilityHost
from easyremote.skills import RemoteSkill


class FakeNode:
    def __init__(self) -> None:
        self.registered_functions = {}
        self.register_calls = []
        self.refresh_calls = 0

    def register(self, func, **kwargs):
        name = kwargs["name"]
        self.register_calls.append((name, kwargs))
        if name in self.registered_functions:
            raise ValueError("function already registered")
        self.registered_functions[name] = func
        return func

    def refresh_gateway_registration_now(self, timeout_seconds: float = 8.0) -> bool:
        self.refresh_calls += 1
        return True


def test_user_device_host_installs_remote_skill_to_local_node():
    node = FakeNode()
    host = UserDeviceCapabilityHost(node, auto_refresh_registration=True)

    host.register_action(
        "camera.take_photo",
        lambda: {"path": "/tmp/photo.jpg"},
        description="Take one photo via user-approved camera API",
    )

    builder = RemoteSkill(name="camera-skill", namespace="device")

    @builder.remote(
        name="take_photo",
        function_name="camera.take_photo",
        metadata={
            "device_action": "camera.take_photo",
            "tags": ["camera", "photo"],
        },
    )
    def take_photo():
        return {}

    installed_name = host.install_skill(builder.export_pipeline(as_json=False))
    assert installed_name == "camera-skill"
    assert node.refresh_calls == 1
    assert "device.camera.take_photo" in node.registered_functions

    registered_fn = node.registered_functions["device.camera.take_photo"]
    assert registered_fn() == {"path": "/tmp/photo.jpg"}

    installed = host.list_installed_skills()["camera-skill"]
    assert installed["capabilities"]["take_photo"]["action_name"] == "camera.take_photo"


def test_user_device_host_requires_declared_local_action():
    node = FakeNode()
    host = UserDeviceCapabilityHost(node)

    builder = RemoteSkill(name="video-skill", namespace="device")

    @builder.remote(
        name="record_video",
        function_name="camera.record_video",
        metadata={"device_action": "camera.record_video"},
    )
    def record_video(duration_seconds: int = 3):
        return duration_seconds

    with pytest.raises(KeyError):
        host.install_skill(builder.export_pipeline(as_json=False))


def test_user_device_host_skips_existing_registration_name():
    node = FakeNode()
    node.registered_functions["device.camera.take_photo"] = lambda: {"path": "existing.jpg"}
    host = UserDeviceCapabilityHost(node, auto_refresh_registration=False)

    host.register_action(
        "camera.take_photo",
        lambda: {"path": "new.jpg"},
    )

    builder = RemoteSkill(name="camera-skill", namespace="device")

    @builder.remote(
        name="take_photo",
        function_name="camera.take_photo",
        metadata={"device_action": "camera.take_photo"},
    )
    def take_photo():
        return {}

    host.install_skill(builder.export_pipeline(as_json=False))
    assert len(node.register_calls) == 0
    assert node.refresh_calls == 0


def test_user_device_host_installs_transferred_code_module():
    node = FakeNode()
    host = UserDeviceCapabilityHost(
        node,
        auto_refresh_registration=False,
        allow_transferred_code=True,
    )

    payload = {
        "schema": "easyremote.remote-skill-pipeline",
        "version": "1.0",
        "skill_name": "dynamic-code-skill",
        "capabilities": [
            {
                "alias": "say_hi",
                "function_name": "user.say_hi",
                "stream": False,
                "load_balancing": True,
                "media_type": "application/json",
                "metadata": {
                    "code_binding": {
                        "module_id": "mod-1",
                        "export": "say_hi_impl",
                    }
                },
            }
        ],
        "runtime_modules": [
            {
                "module_id": "mod-1",
                "language": "python",
                "source": (
                    "def say_hi_impl(name='world'):\n"
                    "    return {'msg': 'hi ' + str(name), 'mode': 'code_transfer'}\n"
                ),
            }
        ],
    }

    installed_name = host.install_skill(payload)
    assert installed_name == "dynamic-code-skill"
    assert "user.say_hi" in node.registered_functions

    result = node.registered_functions["user.say_hi"]("alice")
    assert result == {"msg": "hi alice", "mode": "code_transfer"}

    installed = host.list_installed_skills()["dynamic-code-skill"]
    assert installed["capabilities"]["say_hi"]["binding_mode"] == "code_transfer"
    assert installed["capabilities"]["say_hi"]["action_name"] is None
    assert installed["metadata"]["runtime_modules"] == ["mod-1"]


def test_user_device_host_can_prefer_transferred_code_over_device_actions():
    node = FakeNode()
    host = UserDeviceCapabilityHost(
        node,
        auto_refresh_registration=False,
        prefer_transferred_code=True,
        allow_transferred_code=True,
    )

    host.register_action(
        "say_hi",
        lambda name="world": {"msg": "hi " + str(name), "mode": "device_action"},
        description="Local approved action",
    )

    payload = {
        "schema": "easyremote.remote-skill-pipeline",
        "version": "1.0",
        "skill_name": "dynamic-code-skill",
        "capabilities": [
            {
                "alias": "say_hi",
                "function_name": "user.say_hi",
                "stream": False,
                "load_balancing": True,
                "media_type": "application/json",
                "metadata": {
                    "code_binding": {
                        "module_id": "mod-1",
                        "export": "say_hi_impl",
                    }
                },
            }
        ],
        "runtime_modules": [
            {
                "module_id": "mod-1",
                "language": "python",
                "source": (
                    "def say_hi_impl(name='world'):\n"
                    "    return {'msg': 'hi ' + str(name), 'mode': 'code_transfer'}\n"
                ),
            }
        ],
    }

    installed_name = host.install_skill(payload)
    assert installed_name == "dynamic-code-skill"
    assert "user.say_hi" in node.registered_functions

    result = node.registered_functions["user.say_hi"]("alice")
    assert result == {"msg": "hi alice", "mode": "code_transfer"}

    installed = host.list_installed_skills()["dynamic-code-skill"]
    assert installed["capabilities"]["say_hi"]["binding_mode"] == "code_transfer"
    assert installed["capabilities"]["say_hi"]["action_name"] is None
