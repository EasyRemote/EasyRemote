import base64
import os
import time
from pathlib import Path

_FALLBACK_JPEG_BASE64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////"
    "////////////////////////////////////////////2wBDAf/////////////////////"
    "//////////////////////////////////////////////////////////wAARCAABAAEDAREA"
    "AhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/8QA"
    "FQEBAQAAAAAAAAAAAAAAAAAAAwT/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAP"
    "wCdAB//2Q=="
)

def _resolve_output_path(output_path, default_name):
    raw = str(output_path).strip() or default_name
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def _parse_camera_index(source):
    raw = str(source or "").strip().lower()
    if raw.startswith("camera://") and raw[9:].isdigit():
        return int(raw[9:])
    # "auto", "front-camera", "" => default to 0 for demo purposes
    return 0

def _try_cv2_capture(source, resolution):
    try:
        import cv2  # type: ignore[import-not-found]
    except Exception:
        return None

    index = _parse_camera_index(source)
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        return None

    parts = str(resolution).split("x")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(parts[0]))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(parts[1]))

    # Warm-up reads improve stability on some backends.
    for _ in range(5):
        cap.read()

    ok, frame = cap.read()
    cap.release()
    return frame if ok else None

def take_photo_impl(output_path="photo.jpg", source="front-camera", resolution="1920x1080"):
    output_file = _resolve_output_path(output_path, "photo.jpg")
    frame = _try_cv2_capture(source, resolution)
    if frame is not None:
        try:
            import cv2  # type: ignore[import-not-found]

            cv2.imwrite(str(output_file), frame)
            capture_mode = "camera"
        except Exception:
            output_file.write_bytes(base64.b64decode(_FALLBACK_JPEG_BASE64))
            capture_mode = "placeholder"
    else:
        output_file.write_bytes(base64.b64decode(_FALLBACK_JPEG_BASE64))
        capture_mode = "placeholder"
    return {
        "action": "take_photo",
        "saved_to": str(output_file),
        "source": source,
        "resolution": resolution,
        "capture_mode": "transferred_code",
        "capture_reason": "transferred_runtime_module",
        "captured_at": int(time.time()),
        "status": "ok",
        "capture_backend": capture_mode,
    }

def record_video_impl(duration_seconds=4, output_path="clip.mp4", source="front-camera", resolution="1280x720", fps=30):
    output_file = _resolve_output_path(output_path, "clip.mp4")
    duration_seconds = max(1, int(duration_seconds))
    fps = max(1, min(int(fps), 120))
    frames_written = 0
    capture_backend = "placeholder"
    try:
        import cv2  # type: ignore[import-not-found]

        index = _parse_camera_index(source)
        cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            raise RuntimeError("camera not available")

        parts = str(resolution).split("x")
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
        writer = cv2.VideoWriter(
            str(output_file),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (w, h),
        )
        writer.write(probe)
        frames_written = 1

        interval = 1.0 / float(fps)
        for _ in range(duration_seconds * fps - 1):
            t0 = time.monotonic()
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            writer.write(frame)
            frames_written += 1
            elapsed = time.monotonic() - t0
            if elapsed < interval:
                time.sleep(interval - elapsed)

        writer.release()
        cap.release()
        capture_backend = "camera"
    except Exception:
        output_file.write_bytes(b"EASYREMOTE_PLACEHOLDER_VIDEO")
        frames_written = 0
        capture_backend = "placeholder"
    return {
        "action": "record_video",
        "saved_to": str(output_file),
        "source": source,
        "resolution": resolution,
        "duration_seconds": int(duration_seconds),
        "fps": int(fps),
        "capture_mode": "transferred_code",
        "capture_reason": "transferred_runtime_module",
        "captured_at": int(time.time()),
        "status": "ok",
        "capture_backend": capture_backend,
        "frames_written": frames_written,
    }

def list_devices_impl(scan_max_index=4):
    scan_max_index = max(0, int(scan_max_index))

    # Fallback: environment-provided simulated inventory (works without OpenCV).
    raw = os.getenv("CAMERA_CANDIDATES", "0,1,2,3")
    simulated = []
    for piece in raw.split(","):
        text = piece.strip()
        if text.isdigit():
            simulated.append({"index": int(text), "backend": "simulated"})

    try:
        import cv2  # type: ignore[import-not-found]
    except Exception:
        available = simulated[: scan_max_index + 1]
        return {
            "opencv_available": False,
            "available": available,
            "checked_indices": [item["index"] for item in available],
            "backend_candidates": ["simulated"],
            "attempt_errors": [],
        }

    available = []
    attempt_errors = []
    for i in range(scan_max_index + 1):
        try:
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ok, frame = cap.read()
                if ok and frame is not None:
                    h, w = frame.shape[:2]
                    available.append({"index": i, "backend": "opencv", "width": w, "height": h})
            cap.release()
        except Exception as exc:
            attempt_errors.append({"index": i, "error": str(exc)})

    return {
        "opencv_available": True,
        "available": available or simulated[: scan_max_index + 1],
        "checked_indices": list(range(scan_max_index + 1)),
        "backend_candidates": ["opencv", "simulated"],
        "attempt_errors": attempt_errors,
    }

def stream_video_impl(source="front-camera", frame_count=5, fps=24):
    for index in range(max(1, int(frame_count))):
        yield {
            "stream": "video",
            "frame_index": index,
            "source": source,
            "fps": int(fps),
            "generated_by": "transferred_runtime_module",
        }

def stream_voice_impl(chunk_count=4, sample_rate_hz=16000):
    for index in range(max(1, int(chunk_count))):
        yield {
            "stream": "voice",
            "chunk_index": index,
            "sample_rate_hz": int(sample_rate_hz),
            "pcm16": "transferred-frame-{0}".format(index),
            "generated_by": "transferred_runtime_module",
        }
