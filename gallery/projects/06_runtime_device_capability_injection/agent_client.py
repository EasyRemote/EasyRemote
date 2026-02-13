#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Server-side agent client for runtime device capability injection.

Flow:
1) Pack a runtime skill payload (capabilities + runtime code modules)
2) Push payload to a specific user device node (device.install_remote_skill)
3) Call newly registered functions immediately (photo/video + streaming)

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from easyremote import Client, RemoteSkill  # noqa: E402


def build_camera_runtime_skill_payload() -> Dict[str, Any]:
    skill = RemoteSkill.from_directory(
        Path(__file__).parent / "skills" / "camera-runtime-pack"
    )
    return skill.export_pipeline(as_json=False)


class AgentBotOrchestrator:
    def __init__(
        self,
        gateway_address: str,
        *,
        target_node_id: Optional[str] = None,
        target_user_id: Optional[str] = None,
        photo_source: str = "auto",
        photo_resolution: str = "1280x720",
        camera_scan_max_index: int = 6,
        video_duration_seconds: int = 3,
        video_fps: int = 30,
    ) -> None:
        self._client = Client(gateway_address)
        self._target_node_id = (
            str(target_node_id).strip() if target_node_id is not None else None
        )
        self._target_user_id = (
            str(target_user_id).strip() if target_user_id is not None else None
        )
        self._photo_source = str(photo_source).strip() or "auto"
        self._photo_resolution = str(photo_resolution).strip() or "1280x720"
        self._camera_scan_max_index = max(0, int(camera_scan_max_index))
        self._video_duration_seconds = max(1, int(video_duration_seconds))
        self._video_fps = max(1, min(int(video_fps), 120))

    def _resolve_target_node_id(self) -> str:
        if self._target_node_id:
            return self._target_node_id

        if not self._target_user_id:
            raise ValueError(
                "Provide TARGET_USER_NODE_ID or TARGET_USER_ID to resolve target node"
            )

        matches = self._client.find_nodes(
            required_capabilities=["user:{0}".format(self._target_user_id)],
            required_functions=["device.install_remote_skill"],
        )
        if not matches:
            raise RuntimeError(
                "No online node found for user '{0}'. "
                "Expected capability tag 'user:{0}' and function "
                "'device.install_remote_skill'.".format(self._target_user_id)
            )

        # Pressure-aware selection: choose the least-loaded node for this user.
        matches.sort(
            key=lambda item: (
                float(item.get("current_load", 1.0)),
                str(item.get("node_id", "")),
            )
        )
        return str(matches[0]["node_id"])

    @staticmethod
    def _pick_first_camera_index(inventory: Any) -> Optional[int]:
        if not isinstance(inventory, dict):
            return None
        available = inventory.get("available", [])
        if not isinstance(available, list) or not available:
            return None
        first = available[0]
        if not isinstance(first, dict):
            return None
        index = first.get("index")
        if isinstance(index, int):
            return index
        return None

    def run(self) -> None:
        target_node_id = self._resolve_target_node_id()
        skill_payload = build_camera_runtime_skill_payload()

        install_result = self._client.execute_on_node(
            target_node_id,
            "device.install_remote_skill",
            skill_payload=skill_payload,
        )

        camera_inventory = self._client.execute_on_node(
            target_node_id,
            "user.camera.list_devices",
            scan_max_index=self._camera_scan_max_index,
        )

        selected_photo_source = self._photo_source
        if selected_photo_source in {"auto", "default", ""}:
            index = self._pick_first_camera_index(camera_inventory)
            if index is not None:
                selected_photo_source = "camera://{0}".format(index)

        # Photo call may race with registration propagation; retry briefly.
        photo_result: Optional[Dict[str, Any]] = None
        last_error: Optional[Exception] = None
        for _ in range(8):
            try:
                photo_result = self._client.execute_on_node(
                    target_node_id,
                    "user.camera.take_photo",
                    output_path="customer-selfie.jpg",
                    source=selected_photo_source,
                    resolution=self._photo_resolution,
                )
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.4)
        if photo_result is None:
            raise RuntimeError(
                "Failed to call user.camera.take_photo after dynamic install"
            ) from last_error

        video_result = self._client.execute_on_node(
            target_node_id,
            "user.camera.record_video",
            duration_seconds=self._video_duration_seconds,
            output_path="site-check.mp4",
            source=selected_photo_source,
            resolution=self._photo_resolution,
            fps=self._video_fps,
        )

        video_stream_chunks: List[Dict[str, Any]] = list(
            self._client.stream_on_node(
                target_node_id,
                "user.camera.stream_video",
                source=selected_photo_source,
                frame_count=4,
                fps=24,
            )
        )
        voice_stream_chunks: List[Dict[str, Any]] = list(
            self._client.stream_on_node(
                target_node_id,
                "user.voice.stream_pcm",
                chunk_count=3,
                sample_rate_hz=16000,
            )
        )

        installed_skills = self._client.execute_on_node(
            target_node_id,
            "device.list_installed_skills",
        )

        result = {
            "target_node_id": target_node_id,
            "target_user_id": self._target_user_id,
            "install_result": install_result,
            "camera_inventory": camera_inventory,
            "selected_photo_source": selected_photo_source,
            "photo_result": photo_result,
            "video_result": video_result,
            "video_stream": {
                "chunk_count": len(video_stream_chunks),
                "first_chunk": video_stream_chunks[0] if video_stream_chunks else None,
            },
            "voice_stream": {
                "chunk_count": len(voice_stream_chunks),
                "first_chunk": voice_stream_chunks[0] if voice_stream_chunks else None,
            },
            "installed_skills": installed_skills,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    gateway = os.getenv("EASYREMOTE_GATEWAY_ADDRESS", "127.0.0.1:8084")
    target_node_id = os.getenv("TARGET_USER_NODE_ID")
    target_user_id = os.getenv("TARGET_USER_ID", "demo-user")
    photo_source = os.getenv("PHOTO_SOURCE", "auto")
    photo_resolution = os.getenv("PHOTO_RESOLUTION", "1280x720")
    camera_scan_max_index = int(os.getenv("CAMERA_SCAN_MAX_INDEX", "6"))
    video_duration = int(os.getenv("VIDEO_DURATION", "3"))
    video_fps = int(os.getenv("VIDEO_FPS", "30"))

    AgentBotOrchestrator(
        gateway,
        target_node_id=target_node_id,
        target_user_id=target_user_id,
        photo_source=photo_source,
        photo_resolution=photo_resolution,
        camera_scan_max_index=camera_scan_max_index,
        video_duration_seconds=video_duration,
        video_fps=video_fps,
    ).run()

