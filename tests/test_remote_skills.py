#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for skill-oriented remote capability pipeline helpers.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from types import SimpleNamespace

import pytest

from easyremote.core.nodes.client import ExecutionStrategy
from easyremote.decorators import RemoteFunction
from easyremote.skills import RemoteSkill, pipeline_function, stream_audio_pcm


class FakeSkillClient:
    def __init__(self) -> None:
        self.calls = []

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


def _set_fake_client(fake: FakeSkillClient) -> None:
    RemoteFunction.server_resolver = staticmethod(lambda: None)
    RemoteFunction.client_resolver = staticmethod(lambda: fake)


def _reset_backends() -> None:
    RemoteFunction.server_resolver = staticmethod(lambda: None)
    RemoteFunction.client_resolver = staticmethod(lambda: None)


def test_remote_skill_exports_minimal_pipeline_for_cross_device_transfer():
    skill = RemoteSkill(
        name="voice-skill",
        namespace="assistant",
        gateway_address="127.0.0.1:8080",
    )

    @skill.voice(name="transcribe_live", timeout=20)
    def transcribe_live(audio_bytes):
        return audio_bytes

    @skill.media(
        name="video_frames",
        function_name="vision.frames",
        media_type="video/h264",
        stream=True,
    )
    def video_frames(source):
        return source

    payload = skill.export_pipeline(include_gateway=True, as_json=False)
    assert payload["schema"] == "easyremote.remote-skill-pipeline"
    assert payload["version"] == "1.0"
    assert payload["gateway_address"] == "127.0.0.1:8080"

    specs = {item["alias"]: item for item in payload["capabilities"]}
    assert specs["transcribe_live"]["function_name"] == "assistant.transcribe_live"
    assert specs["transcribe_live"]["stream"] is True
    assert specs["transcribe_live"]["media_type"] == "audio/raw"
    assert specs["transcribe_live"]["codec"] == "pcm16"
    assert specs["video_frames"]["function_name"] == "assistant.vision.frames"
    assert specs["video_frames"]["media_type"] == "video/h264"


def test_remote_skill_pipeline_json_roundtrip_supports_gateway_override():
    skill = RemoteSkill(
        name="voice-skill",
        namespace="assistant",
        gateway_address="127.0.0.1:8080",
    )

    @skill.voice(name="transcribe_live")
    def transcribe_live(audio_bytes):
        return audio_bytes

    pipeline_json = skill.export_pipeline(include_gateway=True)
    imported = RemoteSkill.from_pipeline(
        pipeline_json,
        gateway_address="10.0.0.9:8080",
    )
    imported_specs = imported.capability_specs()
    assert imported_specs["transcribe_live"]["gateway_address"] == "10.0.0.9:8080"
    assert imported_specs["transcribe_live"]["function_name"] == "assistant.transcribe_live"


def test_pipeline_function_rebuilds_remote_callers_on_target_device():
    fake = FakeSkillClient()
    _set_fake_client(fake)
    try:
        payload = {
            "schema": "easyremote.remote-skill-pipeline",
            "version": "1.0",
            "skill_name": "agent-skill",
            "capabilities": [
                {
                    "alias": "classify_text",
                    "function_name": "agent.classify_text",
                    "stream": False,
                    "load_balancing": True,
                    "media_type": "application/json",
                },
                {
                    "alias": "transcribe_stream",
                    "function_name": "agent.transcribe_stream",
                    "stream": True,
                    "load_balancing": True,
                    "media_type": "audio/raw",
                    "codec": "pcm16",
                },
            ],
        }

        pipe = pipeline_function(payload)
        assert sorted(pipe.capabilities()) == ["classify_text", "transcribe_stream"]

        unary_result = pipe("classify_text", "hello")
        stream_chunks = list(pipe("transcribe_stream", "a", "b"))

        assert unary_result["function_name"] == "agent.classify_text"
        assert unary_result["strategy"] == ExecutionStrategy.LOAD_BALANCED.value
        assert unary_result["mode"] == "client"
        assert [chunk["value"] for chunk in stream_chunks] == ["a", "b"]
        assert all(chunk["mode"] == "client_stream" for chunk in stream_chunks)
        assert fake.calls[0][0] == "execute"
        assert fake.calls[1][0] == "stream"
    finally:
        _reset_backends()


def test_stream_audio_pcm_creates_eos_marked_media_frames():
    frames = list(stream_audio_pcm(b"abcdefghij", frame_bytes=4, sample_rate_hz=8000))

    assert len(frames) == 3
    assert frames[0].sequence == 0
    assert frames[-1].sequence == 2
    assert frames[-1].payload == b"ij"
    assert frames[-1].end_of_stream is True
    assert all(frame.media_type == "audio/raw" for frame in frames)
    assert frames[0].metadata["sample_rate_hz"] == 8000
    assert frames[0].metadata["channels"] == 1


def test_remote_skill_get_unknown_capability_raises_key_error():
    skill = RemoteSkill(name="demo-skill")
    with pytest.raises(KeyError):
        skill.get("missing")
