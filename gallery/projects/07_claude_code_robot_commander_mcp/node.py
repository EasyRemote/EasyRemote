"""Publish bounded sandbox-robot actions through a warm provider process."""

import threading
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass

from easyremote import ComputeNode, Context

node = ComputeNode(namespace="er")


@dataclass
class RobotState:
    position_cm: int = 0
    battery_percent: int = 100


class SandboxRobot:
    def __init__(self) -> None:
        self._state = RobotState()
        self._lock = threading.Lock()

    def move(self, distance_cm: int) -> dict[str, int]:
        if distance_cm == 0 or not -100 <= distance_cm <= 100:
            raise ValueError("distance_cm must be between -100 and 100, excluding 0")
        with self._lock:
            destination = self._state.position_cm + distance_cm
            if not -1_000 <= destination <= 1_000:
                raise ValueError("move would leave the -1,000..1,000 cm test track")
            energy = max(1, abs(distance_cm) // 10)
            if self._state.battery_percent < energy:
                raise ValueError("robot battery is too low for this move")
            self._state.position_cm = destination
            self._state.battery_percent -= energy
            return asdict(self._state)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return asdict(self._state)


ROBOT = SandboxRobot()


@node.register(description="Move a sandbox robot within explicit local bounds.")
def move_robot(ctx: Context, distance_cm: int) -> dict[str, str | int]:
    return {
        **ROBOT.move(distance_cm),
        "requested_by": ctx.caller,
        "invocation_id": ctx.invocation_id,
    }


@node.register(description="Stream a finite sequence of robot telemetry.")
def robot_telemetry(samples: int = 3) -> Iterator[dict[str, int]]:
    if not 1 <= samples <= 10:
        raise ValueError("samples must be between 1 and 10")
    for sequence in range(1, samples + 1):
        yield {"sequence": sequence, **ROBOT.snapshot()}
        time.sleep(0.1)


if __name__ == "__main__":
    node.serve()
