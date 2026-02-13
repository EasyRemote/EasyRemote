#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for user-facing remote agent service with installable skills.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from types import SimpleNamespace

import pytest

from easyremote.agent_service import RemoteAgentService
from easyremote.core.nodes.client import ExecutionStrategy
from easyremote.decorators import RemoteFunction
from easyremote.skills import RemoteSkill


class FakeAgentClient:
    def __init__(self) -> None:
        self.calls = []
        self.nodes = []

    def execute_with_context(self, context, *args, **kwargs):
        self.calls.append(("execute", context, args, kwargs))
        return SimpleNamespace(
            result={
                "function_name": context.function_name,
                "strategy": context.strategy.value,
                "args": list(args),
                "kwargs": kwargs,
                "mode": "client",
            }
        )

    def stream_with_context(self, context, *args, **kwargs):
        self.calls.append(("stream", context, args, kwargs))
        for index, value in enumerate(args):
            yield {
                "function_name": context.function_name,
                "strategy": context.strategy.value,
                "index": index,
                "value": value,
                "mode": "client_stream",
            }

    def execute_on_node(self, node_id, function_name, *args, **kwargs):
        self.calls.append(("execute_on_node", node_id, function_name, args, kwargs))
        return {
            "node_id": node_id,
            "function_name": function_name,
            "args": list(args),
            "kwargs": kwargs,
            "mode": "client_direct",
        }

    def stream_on_node(self, node_id, function_name, *args, **kwargs):
        self.calls.append(("stream_on_node", node_id, function_name, args, kwargs))
        for index, value in enumerate(args):
            yield {
                "node_id": node_id,
                "function_name": function_name,
                "index": index,
                "value": value,
                "mode": "client_stream_direct",
            }

    def find_nodes(self, *, required_capabilities=None, required_functions=None):
        required_capabilities = set(required_capabilities or [])
        required_functions = set(required_functions or [])

        matched = []
        for node in self.nodes:
            capabilities = set(node.get("capabilities", []))
            functions = set(node.get("functions", []))
            if required_capabilities and not required_capabilities.issubset(capabilities):
                continue
            if required_functions and not required_functions.issubset(functions):
                continue
            matched.append(node)
        return matched


def _set_fake_client(fake: FakeAgentClient) -> None:
    RemoteFunction.server_resolver = staticmethod(lambda: None)
    RemoteFunction.client_resolver = staticmethod(lambda: fake)


def _reset_backends() -> None:
    RemoteFunction.server_resolver = staticmethod(lambda: None)
    RemoteFunction.client_resolver = staticmethod(lambda: None)


def test_remote_agent_service_installs_skill_and_runs_stream_immediately():
    fake = FakeAgentClient()
    _set_fake_client(fake)
    try:
        builder = RemoteSkill(name="voice-agent", namespace="assistant")

        @builder.voice(name="transcribe_live", languages=("zh-CN", "en-US"))
        def transcribe_live(audio):
            return audio

        service = RemoteAgentService(
            user_id="user-1",
            preferred_language="zh-CN",
            gateway_address="127.0.0.1:8080",
        )

        installed_name = service.install_skill(builder.export_pipeline(as_json=False))
        assert installed_name == "voice-agent"
        assert service.list_skill_names() == ["voice-agent"]
        assert service.list_skills()[0]["capability_count"] == 1

        chunks = list(service.run("voice-agent", "transcribe_live", "c1", "c2"))
        assert [chunk["value"] for chunk in chunks] == ["c1", "c2"]
        assert fake.calls[0][0] == "stream"
    finally:
        _reset_backends()


def test_remote_agent_service_enforces_language_compatibility():
    fake = FakeAgentClient()
    _set_fake_client(fake)
    try:
        builder = RemoteSkill(name="writer", namespace="assistant")

        @builder.remote(name="summarize", languages=("en-US",))
        def summarize(text):
            return text

        service = RemoteAgentService(
            user_id="user-2",
            preferred_language="zh-CN",
            fallback_languages=[],
        )
        service.install_skill(builder.export_pipeline(as_json=False))

        with pytest.raises(ValueError):
            service.run("writer", "summarize", "incident report")

        result = service.run(
            "writer",
            "summarize",
            "incident report",
            language="en-US",
        )
        assert result["function_name"] == "assistant.summarize"
        assert result["strategy"] == ExecutionStrategy.LOAD_BALANCED.value
        assert fake.calls[0][0] == "execute"
    finally:
        _reset_backends()


def test_remote_agent_service_can_install_new_skill_at_runtime():
    fake = FakeAgentClient()
    _set_fake_client(fake)
    try:
        voice_builder = RemoteSkill(name="voice", namespace="assistant")

        @voice_builder.voice(name="transcribe_live", languages=("zh-CN", "en-US"))
        def transcribe_live(audio):
            return audio

        write_builder = RemoteSkill(name="writer", namespace="assistant")

        @write_builder.remote(name="summarize", languages=("zh-CN",))
        def summarize(text):
            return text

        service = RemoteAgentService(user_id="user-3", preferred_language="zh-CN")
        service.install_skill(voice_builder.export_pipeline(as_json=False))

        with pytest.raises(KeyError):
            service.run_any("summarize", "disk full")

        service.install_skill(write_builder.export_pipeline(as_json=False))
        result = service.run_ref("writer/summarize", "disk full")
        assert result["function_name"] == "assistant.summarize"

        capabilities = service.list_capabilities(language="zh-CN")
        capability_names = sorted(item["capability"] for item in capabilities)
        assert capability_names == ["summarize", "transcribe_live"]
    finally:
        _reset_backends()


def test_remote_agent_service_run_with_target_user_resolves_node_and_uses_direct_call():
    fake = FakeAgentClient()
    fake.nodes = [
        {
            "node_id": "node-high-load",
            "capabilities": ["user:user-9"],
            "functions": ["assistant.take_photo"],
            "current_load": 0.8,
        },
        {
            "node_id": "node-low-load",
            "capabilities": ["user:user-9"],
            "functions": ["assistant.take_photo"],
            "current_load": 0.2,
        },
    ]
    _set_fake_client(fake)
    try:
        builder = RemoteSkill(name="camera", namespace="assistant")

        @builder.remote(name="take_photo")
        def take_photo(path):
            return path

        service = RemoteAgentService(user_id="user-9")
        service.install_skill(builder.export_pipeline(as_json=False))
        service._resolve_client = lambda gateway_address=None: fake  # type: ignore[method-assign]

        result = service.run(
            "camera",
            "take_photo",
            "user9.jpg",
            target_user_id="user-9",
        )
        assert result["node_id"] == "node-low-load"
        assert result["mode"] == "client_direct"
        assert fake.calls[0][0] == "execute_on_node"
    finally:
        _reset_backends()


def test_remote_agent_service_run_stream_with_target_node_uses_direct_stream():
    fake = FakeAgentClient()
    _set_fake_client(fake)
    try:
        builder = RemoteSkill(name="voice", namespace="assistant")

        @builder.voice(name="transcribe_live")
        def transcribe_live(audio):
            return audio

        service = RemoteAgentService(user_id="user-3")
        service.install_skill(builder.export_pipeline(as_json=False))
        service._resolve_client = lambda gateway_address=None: fake  # type: ignore[method-assign]

        chunks = list(
            service.run(
                "voice",
                "transcribe_live",
                "c1",
                "c2",
                target_node_id="user-node-7",
            )
        )
        assert [chunk["value"] for chunk in chunks] == ["c1", "c2"]
        assert all(chunk["node_id"] == "user-node-7" for chunk in chunks)
        assert fake.calls[0][0] == "stream_on_node"
    finally:
        _reset_backends()
