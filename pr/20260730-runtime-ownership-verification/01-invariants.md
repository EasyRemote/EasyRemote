Invariants
==========

1. EasyRemote product calls may choose a target, but canonical descriptor refs come from the SDK descriptor provider/resolver.
2. Descriptor refs must include ability URA, version, descriptor hash, and action.
3. EasyRemote may expose result-first ergonomics, but terminal state and receipt proof validation come from `easynet_sdk.InvocationResult` / `easynet_sdk.RuntimeReceipt`.
4. Parent receipt references for context child calls must be derived from SDK `RuntimeReceipt` objects.
5. EasyRemote must not expose or call daemon/Hub lifecycle primitives such as `start_daemon`, `start_hub`, or `DaemonHandle`.
6. The classic `gateway` constructor argument is advisory only; it must not reroute or provision runtime state.
7. `runtime_root_context` is allowed only as the call context for SDK-backed runtime system adapters: descriptor listing, runtime ability invocation, and receipt trace. It must not become a public invocation derivation shortcut.
