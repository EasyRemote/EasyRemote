# Intent

Align EasyRemote's SDK identity test facade with the current EasyNet-Cli
Daemon SDK publication/addressing boundary.

The SDK now requires Resource URAs to be built from `owner_ura + path` and
Publication user filtering to consume Axon-delegated `parse_ura` projection
components. EasyRemote tests must model that facade contract instead of the old
`realm + owner_id + path` helper shape.
