# EasyRemote SDK Runtime Identity Projection

## Intent

Move EasyRemote local identity loading onto the EasyNet-Cli Python SDK runtime
environment projection.

EasyRemote remains the Remote product facade. It may expose `LocalIdentity` to
its own product API, but it must not interpret daemon credentials as a second
runtime identity model.

## Scope

- Keep public `LocalIdentity` behavior compatible.
- Preserve `read_credentials()` as a compatibility function while sourcing its
  data from the SDK projection.
- Keep URA construction delegated through `_sdk_identity`.

## Out of scope

- Daemon lifecycle start/stop changes.
- Product Mission/Control/Pipeline redesign.
- Private-key access or signing.
