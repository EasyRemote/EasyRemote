# EasyRemote diagnostics

## Contents

- Triage order
- Identity projection failures
- Caller identity failures
- Authority failures
- Signer failures
- Deployment and route failures
- Stream failures
- Hub publication failures

## Triage order

Start read-only and shallow-to-deep:

```bash
easyremote doctor
easynet status
easynet abilities
```

Then confirm the provider reports `Local active`, the caller uses the same
function name and call shape, and both projects resolve the intended EasyRemote
and EasyNet SDK versions.

## Identity projection failures

Symptom: SDK identity projection rejects unknown fields from
`credentials.json`.

Action: never pass the credentials document to a public identity projection
API. Construct clients through `Client` or the SDK environment so the SDK reads
and projects its own runtime identity.

## Caller identity failures

Symptom: the daemon does not recognize a caller such as a local username.

Action: do not use account names like `dev` as User principals. The paired
identity uses an immutable `user_id` UUID and its canonical User URA. Let
`LocalIdentity` and the SDK environment provide it.

## Authority failures

Symptom: runtime-state, descriptor, capability-directory, or local Device
Resource calls fail with missing or mismatched authority.

Action:

- Give `Client` an explicit invocation derivation policy such as
  `FreshRoot(ResolvedTargetSubject())`.
- Do not mint `x-runtime-delegation` or `x-runtime-session-authority` in
  EasyRemote code.
- Update and test the SDK authority provider if a new protected subject shape
  is introduced.
- Keep Device Resource subject, device-sponsored callee, caller User, action,
  ability scope, nonce-derived session, and expiry bound exactly.

## Signer failures

Symptom: prepared signer mode does not match the signer handle, or the daemon
rejects a signature produced by a legacy runtime signer.

Action: use the local runtime signer provider. It resolves the active
key-service managed signing key for the canonical caller. Do not enumerate key
inventory, use a legacy fallback, or override signer id and policy reference in
prepare options.

## Deployment and route failures

Symptom: `@node.register` reports local activation but calls fail with an
unbound route, negative route, or owner offline error.

Action:

1. Confirm the provider process is still running and its lease has not expired.
2. Confirm descriptor call mode matches RPC, stream, or bidi usage.
3. Confirm the daemon is built with dynamic deployment execution-index binding.
4. Confirm redeploy removed the previous call mode.
5. Inspect daemon catalogue/runtime tests rather than adding a client retry or
   bypass route.

## Stream failures

Symptom: HTTP/2 `RST_STREAM(PROTOCOL_ERROR)` or raw media corruption.

Action: keep EasyRemote on the SDK C ABI transport. The base
`runtime_abi_version()` may report 7 while feature discovery advertises the
additive `runtime_invocation_stream_open_v8` raw-payload symbol. Do not open a
facade-owned direct Axon gRPC stream or base64-wrap `StreamFrame` payloads.

## Hub publication failures

Symptom: provider says `Realm advertisement pending`, while local calls work.

Action: treat local activation and realm publication as different states.
Check Hub reachability, trust material, and the daemon session supervisor.
Do not claim cross-device success until a live Hub and both endpoint runtimes
complete the invocation.
