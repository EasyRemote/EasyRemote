"""Consume exact image bytes from one paired camera device."""

import os
from collections.abc import Iterator
from pathlib import Path

from easyremote import (
    Client,
    FreshRoot,
    ResolvedTargetSubject,
    StreamFrame,
    remote,
)

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))


@remote(client=client, node=os.getenv("EASYREMOTE_CAMERA_NODE"))
def camera_frames(
    frame_count: int = 3,
    width: int = 64,
    height: int = 48,
) -> Iterator[StreamFrame]: ...


if __name__ == "__main__":
    output = Path("captures")
    output.mkdir(exist_ok=True)
    for index, frame in enumerate(camera_frames.stream(frame_count=3), start=1):
        assert isinstance(frame, StreamFrame)
        path = output / f"frame-{index}.pgm"
        path.write_bytes(frame.payload)
        print(path, frame.content_type, len(frame.payload), "bytes")
