"""EasyRemote-owned daemon product ability names.

Only actual EasyRemote consumers belong here. Generic Invocation construction,
addressing, signing, and transport remain owned by easynet-sdk.
"""

from enum import StrEnum


class MissionAbility(StrEnum):
    RUN = "mission.run"
    TRACK = "mission.track"
    CANCEL = "mission.cancel"
    EVENTS = "mission.events"


class AgentAbility(StrEnum):
    START = "agent.start"
    LIST = "agent.list"
    STOP = "agent.stop"
    REFRESH = "agent.refresh"
