#!/usr/bin/env python3
"""Streaming quickstart — recreated from the v1 demo, status included.

The v1 ``remote_stream_quickstart.py`` showed ``@remote(stream=True)``
over EasyRemote's own gRPC plane. In v2 the transport plane belongs to
the EasyNet daemon: the client stream surface exists
(``client.stream()`` / ``client.session()`` ride ``InvokeStream`` /
``InvokeBidi``), but *producing* streams from a registered Python
generator needs the daemon host-attach protocol (EasyNet-Cli PR-1) —
today's device-ability exchange is one stdin/stdout round trip.

This demo therefore does two honest things:

1. registers a generator and shows the loud, actionable rejection —
   the contract you can rely on instead of a silent buffer-everything;
2. shows the consumer surface that already exists, ready for the day
   the producer side lands.
"""

from collections.abc import Iterator

from easyremote import ComputeNode, Unavailable

node = ComputeNode()


def stream_video_frames(source: str) -> Iterator[bytes]:
    """A generator producer — the post-PR-1 shape."""
    yield from (f"frame-{i}@{source}".encode() for i in range(3))


def main() -> None:
    print("== producer side ==")
    try:
        node.register(stream_video_frames)
    except Unavailable as exc:
        print(f"  register(stream_video_frames) -> {exc.kind}/{exc.reason}")
        print(f"  {exc}")

    print()
    print("== consumer side (surface exists today) ==")
    print("  with Client().stream('camera.watch', source='lobby') as frames:")
    print("      for frame in frames: ...")
    print()
    print("  Wired to daemon InvokeStream — point it at any stream ability")
    print("  the daemon exposes; Python-generator producers unlock with")
    print("  the host-attach protocol (EasyNet-Cli PR-1).")

    # Uncomment against a daemon stream ability to consume live frames:
    # with Client().stream("device.watch.health", interval_ms=1000) as frames:
    #     for frame in frames:
    #         print(frame)


if __name__ == "__main__":
    main()
