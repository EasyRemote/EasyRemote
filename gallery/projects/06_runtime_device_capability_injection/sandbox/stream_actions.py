#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Device actions for streaming operations (video frames, voice PCM).
Discovered automatically by ``UserDeviceCapabilityHost.load_sandbox()``.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterator

from easyremote import device_action


@device_action(name="camera.stream_video", description="Stream video frames")
def stream_video(
    source: str = "front-camera",
    frame_count: int = 5,
    fps: int = 24,
) -> Iterator[Dict[str, Any]]:
    for i in range(max(1, int(frame_count))):
        yield {
            "stream": "video",
            "frame_index": i,
            "source": source,
            "fps": int(fps),
            "node_time": int(time.time()),
        }


@device_action(name="voice.stream_pcm", description="Stream voice PCM")
def stream_voice(
    chunk_count: int = 4,
    sample_rate_hz: int = 16000,
) -> Iterator[Dict[str, Any]]:
    for i in range(max(1, int(chunk_count))):
        yield {
            "stream": "voice",
            "chunk_index": i,
            "sample_rate_hz": int(sample_rate_hz),
            "pcm16": "frame-{0}".format(i),
        }

