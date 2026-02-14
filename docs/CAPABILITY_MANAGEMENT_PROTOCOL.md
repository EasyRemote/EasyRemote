# Capability Management Protocol (CMP)

EasyRemote already provides dynamic node discovery (join/leave) via gateway
registration + heartbeat timeout removal.

This document defines a small, reserved-function "protocol surface" for
capability/skill CRUD on user nodes, so both agent-side and user-side software
can rely on stable endpoints.

## Terms

- **Node capability (tag)**: A string in `node_capabilities` used for routing and
  filtering nodes (e.g. `user:alice`, `device`, `gpu`). These are returned by
  `ListNodes`.
- **Ability / Function**: A remotely invokable registered function on a node
  (e.g. `user.camera.take_photo`).
- **RemoteSkill**: A portable pipeline payload describing capabilities (aliases)
  and their remote `function_name` plus optional transferred runtime code.

## Transport

CMP is not a new wire format. It is a set of reserved function names that are
registered on a compute node and called through the existing EasyRemote RPC path
(`Client.execute_on_node`, `Client.stream_on_node`, MCP tools, A2A task.*).

## Required Node Endpoints (User Device)

These endpoints are provided by `UserDeviceCapabilityHost.register_skill_endpoints()`.

Note: function names below are the defaults. You can override them at
registration time, but for interoperability you should keep these stable.

### `device.install_remote_skill`

Install or update (upsert) a `RemoteSkill` payload on a user node and register
all described `function_name` handlers locally.

Request kwargs:

- `skill_payload` (object): exported pipeline payload (dict)
- `replace_existing_skill` (bool, default `true`): if the same skill name is
  already installed, uninstall the previous version first (unregistering only
  functions that were registered by that install).

Response:

- `installed_skill` (string)
- `installed_skills` (object): map `{skill_name -> installed_record}`
- `capability_host_status` (object): snapshot returned by `device.get_capability_host_status`
- `node_id` (string, optional)
- `node_functions` (array[string], optional)

### `device.uninstall_remote_skill`

Remove an installed skill from the node and (optionally) unregister functions
that were registered by that skill install.

Request args/kwargs:

- `skill_name` (string)
- `unregister_functions` (bool, default `true`)

Response:

- `skill_name` (string)
- `uninstalled` (bool)
- `installed_skills` (object)
- `capability_host_status` (object): snapshot returned by `device.get_capability_host_status`
- `node_id` (string, optional)
- `node_functions` (array[string], optional)

### `device.list_installed_skills`

Read all installed skills on the node.

Response:

- `{skill_name -> installed_record}`

### `device.list_node_functions`

Read all registered node functions (abilities) and lightweight metadata.

Response:

- `node_id` (string, optional)
- `capability_host_status` (object): snapshot returned by `device.get_capability_host_status`
- `function_count` (int)
- `functions` (array[object]): `{name, tags?, description?, version?, ...}`

### `device.get_capability_host_status` (recommended)

Agent-facing diagnostics endpoint to understand what the user node can accept.

Request kwargs:

- `include_actions` (bool, default `false`)
- `include_installed_skills` (bool, default `false`)

Response (high-level):

- `node_id` (string|null)
- `flags` (object): `{prefer_transferred_code, allow_transferred_code, auto_consent, ...}`
- `action_count` (int)
- `installed_skill_count` (int)
- `sandbox` (object): last sandbox load attempt status
- `sandbox_module_count` (int): number of imported sandbox modules currently held

This is the intended place to surface conditions like:
- sandbox folder missing (`sandbox.loaded=false`, `sandbox.error_type=NotADirectoryError`)
- code transfer disabled (`flags.allow_transferred_code=false`)

## Compute Node Requirements

To support delete/update of abilities, compute nodes must support unregistering
functions at runtime.

EasyRemote provides:

- `ComputeNode.unregister(function_name) -> bool`
- `ComputeNode.register(..., replace: bool = false)` to update handlers in place
  when needed.

Callers should refresh gateway registration after changes (the device host does
this automatically for install/uninstall endpoints).

## Join/Leave Semantics

- Join: node calls `RegisterNode` on gateway during startup, then sends heartbeats.
- Leave: gateway removes nodes that stop heartbeating past
  `heartbeat_timeout_seconds` and they disappear from `ListNodes`.

## Security Notes

- Transferred runtime code execution is opt-in on user devices
  (`allow_transferred_code=True`) and can require explicit user consent
  (`requires_user_consent` metadata + consent callback).
