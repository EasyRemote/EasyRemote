#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Device actions for camera operations (photo, video, device listing).
Discovered automatically by ``UserDeviceCapabilityHost.load_sandbox()``.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any, Dict

from easyremote import device_action

_FALLBACK_JPEG_BASE64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////"
    "////////////////////////////////////////////2wBDAf/////////////////////"
    "//////////////////////////////////////////////////////////wAARCAABAAEDAREA"
    "AhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/8QA"
    "FQEBAQAAAAAAAAAAAAAAAAAAAwT/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAP"
    "wCdAB//2Q=="
)


def _output_path(raw: str, default: str) -> Path:
    path = Path(raw.strip() or default).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _try_cv2_capture(source: str, resolution: str) -> Any | None:
    """Try to capture one frame with OpenCV; return frame or None."""
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        return None
    index = 0
    raw = source.strip().lower()
    if raw.startswith("camera://") and raw[9:].isdigit():
        index = int(raw[9:])
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        return None
    parts = resolution.split("x")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(parts[0]))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(parts[1]))
    for _ in range(5):
        cap.read()
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


@device_action(name="camera.take_photo", description="Capture one photo")
def take_photo(
    output_path: str = "photo.jpg",
    source: str = "front-camera",
    resolution: str = "1920x1080",
) -> Dict[str, Any]:
    out = _output_path(output_path, "photo.jpg")
    frame = _try_cv2_capture(source, resolution)
    if frame is not None:
        import cv2  # type: ignore[import-not-found]

        cv2.imwrite(str(out), frame)
        mode = "camera"
        reason = None
    else:
        out.write_bytes(base64.b64decode(_FALLBACK_JPEG_BASE64))
        mode = "placeholder"
        reason = "camera_open_failed_or_opencv_missing"
    return {
        "action": "take_photo",
        "saved_to": str(out),
        "source": source,
        "resolution": resolution,
        "capture_mode": mode,
        "capture_reason": reason,
        "captured_at": int(time.time()),
        "status": "ok",
    }


@device_action(name="camera.record_video", description="Record video clip")
def record_video(
    duration_seconds: int = 5,
    output_path: str = "clip.mp4",
    source: str = "front-camera",
    resolution: str = "1280x720",
    fps: int = 30,
) -> Dict[str, Any]:
    out = _output_path(output_path, "clip.mp4")
    duration_seconds = max(1, int(duration_seconds))
    fps = max(1, min(int(fps), 120))
    try:
        import cv2  # type: ignore[import-not-found]

        index = 0
        raw = source.strip().lower()
        if raw.startswith("camera://") and raw[9:].isdigit():
            index = int(raw[9:])
        cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            raise RuntimeError("camera not available")
        parts = resolution.split("x")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(parts[0]))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(parts[1]))
        for _ in range(5):
            cap.read()
        ok, probe = cap.read()
        if not ok or probe is None:
            cap.release()
            raise RuntimeError("camera read failed")
        h, w = probe.shape[:2]
        writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        writer.write(probe)
        written = 1
        interval = 1.0 / fps
        for _ in range(duration_seconds * fps - 1):
            t0 = time.monotonic()
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            writer.write(frame)
            written += 1
            elapsed = time.monotonic() - t0
            if elapsed < interval:
                time.sleep(interval - elapsed)
        writer.release()
        cap.release()
        mode = "camera"
        reason = None
    except Exception:
        out.write_bytes(b"EASYREMOTE_PLACEHOLDER_VIDEO")
        written = 0
        mode = "placeholder"
        reason = "camera_open_failed_or_opencv_missing"
    return {
        "action": "record_video",
        "saved_to": str(out),
        "source": source,
        "resolution": resolution,
        "duration_seconds": duration_seconds,
        "fps": fps,
        "capture_mode": mode,
        "capture_reason": reason,
        "frames_written": written,
        "captured_at": int(time.time()),
        "status": "ok",
    }


@device_action(name="camera.list_devices", description="Probe camera devices")
def list_devices(scan_max_index: int = 4) -> Dict[str, Any]:
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        return {
            "opencv_available": False,
            "available": [],
            "checked_indices": list(range(scan_max_index + 1)),
        }
    available = []
    for i in range(max(0, int(scan_max_index)) + 1):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                h, w = frame.shape[:2]
                available.append({"index": i, "width": w, "height": h})
        cap.release()
    return {
        "opencv_available": True,
        "available": available,
        "checked_indices": list(range(scan_max_index + 1)),
    }

