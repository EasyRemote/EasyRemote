#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quickstart for converting local functions into stable remote + stream calls.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from easyremote import remote
from easyremote.core.nodes.client import set_default_gateway

# One-time stable gateway setup. Retry/circuit breaker are built into the client.
set_default_gateway("127.0.0.1:8080")


@remote(function_name="transcribe_audio", load_balancing=True, timeout=30)
def transcribe_audio(path: str) -> str:
    return path


@remote(function_name="stream_video_frames", load_balancing=True, stream=True, timeout=60)
def stream_video_frames(source: str):
    return source


def main() -> None:
    print("transcribe_audio ->", transcribe_audio("meeting.wav"))

    print("stream_video_frames ->")
    for frame in stream_video_frames("camera://lobby"):
        print("  chunk:", frame)


if __name__ == "__main__":
    main()
