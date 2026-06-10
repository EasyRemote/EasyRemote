---
name: robot-runtime-pack
namespace: user
runtime_module: runtime.py
module_id: robot-runtime-module-v1

capabilities:
  deploy_plan:
    type: remote
    function_name: robot.deploy_plan
    languages: [zh-CN, en-US]
    code_export: deploy_plan_impl
    metadata:
      device_action: robot.deploy_plan
      tags: [robot, deploy, runtime-install]
      requires_user_consent: true

  set_mode:
    type: remote
    function_name: robot.set_mode
    languages: [zh-CN, en-US]
    code_export: set_mode_impl
    metadata:
      device_action: robot.set_mode
      tags: [robot, mode, runtime-install]
      requires_user_consent: true

  execute_action:
    type: remote
    function_name: robot.execute_action
    languages: [zh-CN, en-US]
    code_export: execute_action_impl
    metadata:
      device_action: robot.execute_action
      tags: [robot, action, runtime-install]
      requires_user_consent: true

  get_status:
    type: remote
    function_name: robot.get_status
    languages: [zh-CN, en-US]
    code_export: get_status_impl
    metadata:
      device_action: robot.get_status
      tags: [robot, status, runtime-install]
      requires_user_consent: false

  stream_telemetry:
    type: media
    function_name: robot.stream_telemetry
    stream: true
    media_type: application/json
    languages: [zh-CN, en-US]
    code_export: stream_telemetry_impl
    metadata:
      device_action: robot.stream_telemetry
      tags: [robot, telemetry, stream, runtime-install]
      requires_user_consent: false
---

# Robot Runtime Pack

Runtime capability pack for remote robot deployment and control on client-sandbox nodes.
