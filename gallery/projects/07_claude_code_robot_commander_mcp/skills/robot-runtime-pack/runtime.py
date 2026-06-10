from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_STATE: Dict[str, Any] = {
    "mode": "idle",
    "battery": 100.0,
    "pose": {"x": 0.0, "y": 0.0, "heading_deg": 0.0},
    "mission": None,
    "last_action": None,
    "history": [],
}


def _resolve_path(output_path: str, default_name: str) -> Path:
    path = Path(str(output_path).strip() or default_name).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_history(action: str, details: Dict[str, Any]) -> None:
    _STATE["last_action"] = action
    _STATE["history"].append(
        {
            "action": action,
            "timestamp": int(time.time()),
            "details": details,
            "engine": "transferred_runtime_module",
        }
    )


def deploy_plan_impl(
    mission_id: str = "demo-mission",
    steps: Optional[List[str]] = None,
    output_path: str = "robot-mission.json",
) -> Dict[str, Any]:
    normalized_steps = [str(item).strip() for item in (steps or []) if str(item).strip()]
    if not normalized_steps:
        normalized_steps = ["boot", "navigate", "report"]

    mission = {
        "mission_id": str(mission_id).strip() or "demo-mission",
        "steps": normalized_steps,
        "deployed_at": int(time.time()),
        "engine": "transferred_runtime_module",
    }

    output_file = _resolve_path(output_path, "robot-mission.json")
    output_file.write_text(json.dumps(mission, ensure_ascii=False, indent=2), encoding="utf-8")

    _STATE["mission"] = mission
    _STATE["mode"] = "ready"
    _append_history("deploy_plan", {"output_path": str(output_file)})

    return {
        "status": "ok",
        "mission": mission,
        "saved_to": str(output_file),
        "binding": "code_transfer",
    }


def set_mode_impl(mode: str = "auto", reason: str = "") -> Dict[str, Any]:
    target = str(mode).strip().lower() or "auto"
    if target not in {"idle", "ready", "auto", "manual", "hold"}:
        raise ValueError("unsupported mode: {0}".format(mode))

    _STATE["mode"] = target
    _append_history("set_mode", {"mode": target, "reason": str(reason)})

    return {
        "status": "ok",
        "mode": target,
        "reason": str(reason),
        "binding": "code_transfer",
    }


def execute_action_impl(
    action: str = "forward",
    distance_m: float = 1.0,
    turn_deg: float = 0.0,
) -> Dict[str, Any]:
    name = str(action).strip().lower() or "forward"
    distance = float(distance_m)
    turn = float(turn_deg)

    pose = dict(_STATE["pose"])
    pose["x"] = float(pose["x"]) + distance
    pose["heading_deg"] = float(pose["heading_deg"]) + turn
    _STATE["pose"] = pose
    _STATE["battery"] = max(0.0, float(_STATE["battery"]) - abs(distance) * 0.8)

    _append_history(
        "execute_action",
        {
            "action": name,
            "distance_m": distance,
            "turn_deg": turn,
        },
    )

    return {
        "status": "ok",
        "action": name,
        "pose": pose,
        "battery": round(float(_STATE["battery"]), 2),
        "binding": "code_transfer",
    }


def get_status_impl() -> Dict[str, Any]:
    return {
        "status": "ok",
        "mode": _STATE["mode"],
        "battery": round(float(_STATE["battery"]), 2),
        "pose": dict(_STATE["pose"]),
        "mission": dict(_STATE["mission"]) if isinstance(_STATE["mission"], dict) else None,
        "last_action": _STATE["last_action"],
        "history_size": len(_STATE["history"]),
        "binding": "code_transfer",
    }


def stream_telemetry_impl(frame_count: int = 3, interval_ms: int = 80):
    count = max(1, int(frame_count))
    sleep_seconds = max(0.0, float(interval_ms) / 1000.0)

    for index in range(count):
        yield {
            "type": "telemetry",
            "seq": index,
            "mode": _STATE["mode"],
            "battery": round(max(0.0, float(_STATE["battery"]) - index * 0.2), 2),
            "pose": dict(_STATE["pose"]),
            "timestamp": int(time.time()),
            "source": "transferred_runtime_module",
        }
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
