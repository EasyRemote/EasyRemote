"""Exercise one bounded robot action and its telemetry stream."""

import os
from collections.abc import Iterator
from pprint import pprint

from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))
robot_node = os.getenv("EASYREMOTE_ROBOT_NODE")


@remote(client=client, node=robot_node)
def move_robot(distance_cm: int) -> dict[str, str | int]: ...


@remote(client=client, node=robot_node)
def robot_telemetry(samples: int = 3) -> Iterator[dict[str, int]]: ...


if __name__ == "__main__":
    pprint(move_robot(100))
    for sample in robot_telemetry.stream(samples=3):
        pprint(sample)
