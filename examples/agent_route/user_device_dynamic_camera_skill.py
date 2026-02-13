#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quickstart for remote agent installing camera/video capabilities on user device.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from easyremote import ComputeNode, RemoteSkill, UserDeviceCapabilityHost


def main() -> None:
    # User device compute node (already connected to gateway in real deployment).
    node = ComputeNode("127.0.0.1:8080", node_id="user-laptop-node")
    host = UserDeviceCapabilityHost(node)

    # User-approved local actions (camera APIs).
    def take_photo(output_path: str = "photo.jpg"):
        # Replace with your camera SDK call.
        return {"saved_to": output_path, "status": "ok"}

    def record_video(duration_seconds: int = 5, output_path: str = "clip.mp4"):
        # Replace with your camera SDK call.
        return {
            "saved_to": output_path,
            "duration_seconds": duration_seconds,
            "status": "ok",
        }

    host.register_action("camera.take_photo", take_photo, description="Capture one photo")
    host.register_action("camera.record_video", record_video, description="Record one video clip")

    # Server-side agent prepares a new skill payload and pushes to this user device.
    remote_skill = RemoteSkill(name="camera-service", namespace="user")

    @remote_skill.remote(
        name="take_photo",
        function_name="camera.take_photo",
        metadata={"device_action": "camera.take_photo"},
    )
    def remote_take_photo(path: str):
        return path

    @remote_skill.remote(
        name="record_video",
        function_name="camera.record_video",
        metadata={"device_action": "camera.record_video"},
    )
    def remote_record_video(duration_seconds: int, output_path: str):
        return {"duration_seconds": duration_seconds, "output_path": output_path}

    payload = remote_skill.export_pipeline(as_json=False)
    installed = host.install_skill(payload)

    print("installed skill:", installed)
    print("installed capabilities:", host.list_installed_skills())
    print("node functions:", sorted(node.registered_functions.keys()))
    print("serve this node to expose new capabilities remotely")


if __name__ == "__main__":
    main()
