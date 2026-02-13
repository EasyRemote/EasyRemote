---
name: camera-runtime-pack
namespace: user
runtime_module: runtime.py
module_id: camera-runtime-module-v1

capabilities:
  take_photo:
    type: remote
    function_name: camera.take_photo
    languages: [zh-CN, en-US]
    code_export: take_photo_impl
    metadata:
      device_action: camera.take_photo
      tags: [camera, photo, runtime-install]
      requires_user_consent: true

  record_video:
    type: remote
    function_name: camera.record_video
    languages: [zh-CN, en-US]
    code_export: record_video_impl
    metadata:
      device_action: camera.record_video
      tags: [camera, video, runtime-install]
      requires_user_consent: true

  list_devices:
    type: remote
    function_name: camera.list_devices
    languages: [zh-CN, en-US]
    code_export: list_devices_impl
    metadata:
      device_action: camera.list_devices
      tags: [camera, probe, runtime-install]
      requires_user_consent: false

  stream_video:
    type: media
    function_name: camera.stream_video
    stream: true
    media_type: video/h264
    languages: [zh-CN, en-US]
    code_export: stream_video_impl
    metadata:
      device_action: camera.stream_video
      tags: [camera, stream, runtime-install]
      requires_user_consent: true

  stream_voice:
    type: voice
    function_name: voice.stream_pcm
    languages: [zh-CN, en-US]
    codec: pcm16
    code_export: stream_voice_impl
    metadata:
      device_action: voice.stream_pcm
      tags: [voice, stream, runtime-install]
      requires_user_consent: true
---

# Camera Runtime Pack

远程 agent 向用户设备注入相机/语音能力的 runtime skill。
