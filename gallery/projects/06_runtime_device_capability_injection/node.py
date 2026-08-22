"""Publish a finite binary camera stream from an edge device."""

from collections.abc import Iterator

from easyremote import ComputeNode, StreamFrame

node = ComputeNode(namespace="er")


def capture_frame(sequence: int, width: int, height: int) -> bytes:
    header = f"P5\n{width} {height}\n255\n".encode("ascii")
    pixels = bytes(
        (x * 3 + y * 5 + sequence * 17) % 256
        for y in range(height)
        for x in range(width)
    )
    return header + pixels


@node.register(description="Stream a bounded sequence of raw grayscale images.")
def camera_frames(
    frame_count: int = 3,
    width: int = 64,
    height: int = 48,
) -> Iterator[StreamFrame]:
    if not 1 <= frame_count <= 10:
        raise ValueError("frame_count must be between 1 and 10")
    if not 16 <= width <= 256 or not 16 <= height <= 256:
        raise ValueError("width and height must be between 16 and 256")
    for sequence in range(frame_count):
        yield StreamFrame(
            capture_frame(sequence, width, height),
            "image/x-portable-graymap",
        )


if __name__ == "__main__":
    node.serve()
