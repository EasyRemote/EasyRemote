# Read a Device Capability Without Opening the Device

## Concrete use case

An edge application needs several camera frames from a paired device behind
NAT. The caller should request a finite count and receive exact image bytes; it
should not obtain a device shell, raw camera handle, filesystem path, or
long-lived port. The MVP permits 1–10 grayscale frames with dimensions between
16 and 256 pixels and identifies every binary payload as a portable graymap.

The provider generates deterministic frames so no camera package or hardware is
required. A production adapter replaces `capture_frame` with the local camera
SDK while retaining the same bounded stream contract.

## Requirements

- Keep the camera or sensor handle inside the provider process.
- Bound frame count, dimensions, and therefore total output volume.
- Preserve exact bytes and media type in every stream item.
- Let the caller target a paired device by stable device identifier.
- End the stream once with a deterministic terminal outcome.

## Existing approach

Edge teams commonly expose an HTTP camera endpoint, establish a VPN, or grant
remote shell access. Those mechanisms solve machine connectivity rather than
the task. They introduce open ports, device-specific routing, broad authority,
and bespoke binary framing. Preinstalling every possible future action also
increases client complexity and permission pressure.

## EasyRemote approach

The device registers a finite `camera_frames` generator with
`@node.register`. Each yielded `StreamFrame` separates lifecycle metadata from
raw image bytes. The caller binds an `@remote` stub to
`EASYREMOTE_CAMERA_NODE` and consumes the ordinary `.stream(...)` interface.

## Effect

The minimum product result is task-level access to camera output rather than
network-level access to the device. It also exercises the binary server-stream
path carried by the SDK's feature-detected C ABI v8 raw-stream extension. The
base `runtime_abi_version()` remains 7; EasyRemote binds neither ABI directly.
Dynamic capability installation and mobile permission prompts
are broader lifecycle features; this runnable MVP proves the device execution
boundary they would eventually install into.

## Run

```bash
uv sync
uv run python node.py
EASYREMOTE_CAMERA_NODE=camera-1 uv run python client.py
```
