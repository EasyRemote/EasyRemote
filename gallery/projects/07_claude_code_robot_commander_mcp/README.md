# Give an Agent One Robot Action, Not Robot Control

## Concrete use case

A robotics team wants a developer agent to move a sandbox inspection robot and
then read telemetry. The useful authority is much smaller than remote control:
one move between -100 and 100 centimetres, constrained to a -1,000 to 1,000
centimetre test track, followed by at most ten telemetry samples. Every action
result identifies its caller and invocation.

The project uses an in-memory robot protected by a lock, so it runs without
hardware and preserves state while the provider process is warm. Replacing the
two methods with a vendor adapter must not widen the public bounds.

## Requirements

- Expose named actions rather than a general command or vendor SDK tunnel.
- Validate distance, track boundary, battery state, and sample count locally.
- Serialize mutation of the warm robot state under concurrent calls.
- Attribute a physical-style action to caller and invocation identity.
- Provide finite telemetry with a single terminal stream outcome.

## Existing approach

Agent-driven robotics often begins with shell access, ROS network exposure, or
a vendor API key. These interfaces grant broad authority and couple the agent
to device topology. A generated plan may sound precise while the execution
record remains a chat transcript rather than evidence that a constrained action
was admitted and completed.

## EasyRemote approach

The robot node publishes `move_robot` and `robot_telemetry` with
`@node.register`. The commander-side program declares typed `@remote` stubs
bound to `EASYREMOTE_ROBOT_NODE`. The agent layer may decide when to call them,
but it cannot change their validation or obtain the underlying device handle.

## Effect

The MVP proves that an agent can receive one auditable action right instead of
general machine control. It also exposes the next product requirements clearly:
human approval, durable device state, emergency stop, dynamic installation,
MCP presentation, and hardware-specific safety certification. None is hidden
behind simulated gallery code.

## Run

```bash
uv sync
uv run python node.py
EASYREMOTE_ROBOT_NODE=robot-1 uv run python client.py
```
