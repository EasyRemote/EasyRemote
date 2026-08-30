# EasyRemote Concrete Use-Case Gallery

This gallery tests one product claim: a useful local Python function should
become a governed remote capability before its owner has to build and operate a
new service.

The projects are production-shaped minimum viable cases rather than feature
demos. Each one starts from a named user, a bounded task, and a failure in the
usual implementation approach. The provider publishes the task with
`@node.register`; the caller declares the same typed boundary with `@remote`.
Identity, routing, admission, signing, and receipts remain runtime concerns and
are not reimplemented in gallery code.

## Projects

| Project | Primary user | Minimum task | Carrier |
|---|---|---|---|
| [Remote quote](projects/00_basic_remote_math/README.md) | Sales engineering | Calculate one bounded commercial quote | Unary |
| [Shared warm model](projects/01_team_gpu_pool_load_balancing/README.md) | ML engineering | Call a model already resident on a teammate's machine | Unary |
| [Agent tool mesh](projects/02_mcp_tool_mesh/README.md) | Agent platform teams | Call owned CRM and follow-up functions through typed tools | Unary |
| [Incident evidence](projects/03_a2a_incident_copilot/README.md) | SRE | Collect allowlisted diagnosis and finite evidence | Unary + stream |
| [Function marketplace](projects/04_function_marketplace/README.md) | Internal platform teams | Reuse validated business functions without copying code | Unary |
| [Data-resident analysis](projects/05_local_data_residency_ai/README.md) | Regulated data owners | Return a sanitized projection without releasing source data | Unary |
| [Edge camera stream](projects/06_runtime_device_capability_injection/README.md) | Edge application teams | Read finite binary frames from a device behind its runtime | Raw server stream |
| [Bounded robot action](projects/07_claude_code_robot_commander_mcp/README.md) | Robotics agent teams | Execute one constrained action and read telemetry | Unary + stream |
| [Network-native Python library](projects/08_network_native_python_library/README.md) | Data application teams | Import remote semantic operators without cloning their implementation | Unary |

## Independent execution

Every directory is an independent uv project with its own lockfile. From any
project directory:

```bash
uv sync
uv run python node.py
```

After the provider reports readiness, run the caller in a second terminal:

```bash
uv run python client.py
```

Both machines need a paired, running EasyNet runtime. `@node.register` does not
start or pair the daemon. Run `easynet login`,
`easynet device join <pairing-token>`, `easynet runtime start`, and
`easyremote doctor` before the first case.

## Scope

These projects deliberately avoid arbitrary SQL, shell access, filesystem
paths, dynamic code installation, and unrestricted hardware commands. They
demonstrate the smallest safe capability boundary. Scheduling, approval
workflows, MCP presentation, durable job state, and physical-device adapters
can be layered on only after that boundary proves useful.
