#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quickstart for exporting remote capabilities as an agent-consumable pipeline.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from easyremote import RemoteSkill, pipeline_function


builder = RemoteSkill(
    name="voice-agent",
    gateway_address="127.0.0.1:8080",
    namespace="assistant",
)


@builder.voice(name="transcribe_live", timeout=30)
def transcribe_live(audio_payload):
    return audio_payload


@builder.media(
    name="stream_video_frames",
    media_type="video/h264",
    stream=True,
    timeout=60,
)
def stream_video_frames(source):
    return source


def main() -> None:
    # This JSON can be sent to another device by any channel (message queue, file, RPC).
    pipeline_json = builder.export_pipeline(include_gateway=True)

    # On another device: rebuild callable pipeline from the shared payload.
    remote_pipe = pipeline_function(pipeline_json)

    print("capabilities:", remote_pipe.capabilities())
    print(
        "call result:",
        remote_pipe("transcribe_live", b"pcm16-bytes"),
    )

    print("stream result:")
    for chunk in remote_pipe("stream_video_frames", "camera://lobby"):
        print("  chunk:", chunk)


if __name__ == "__main__":
    main()
