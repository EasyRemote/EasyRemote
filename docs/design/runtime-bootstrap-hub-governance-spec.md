# EasyRemote Runtime Bootstrap, Hub Lifecycle, and Governance SPEC

> Status: SPEC v0.1
> Date: 2026-07-13
> Owner: Silan Hu <silan.hu@u.nus.edu>
> Scope: EasyRemote authoring experience, EasyNet-Cli daemon lifecycle boundary, Hub/local-dev onboarding, self-hosted governance, Backend integration
> Nature: Normative product/architecture SPEC. When implementation and this document conflict, either update the implementation or revise this SPEC first.

---

## 0. Core Product Promise

EasyRemote's product promise is not "one more daemon command." The concrete use case is:

> A developer publishes a local Python function as a governable, remotely callable EasyNet capability without learning daemon, Hub, key process, or protocol internals.

The user writes:

```python
from easyremote import ComputeNode

node = ComputeNode()

@node.register
def add(a: int, b: int) -> int:
    return a + b

node.serve()
```

The system prepares the paired device runtime, starts the warm host, publishes the capability, and makes it callable through the daemon-owned EasyNet Invocation path.

This SPEC separates five concrete product paths:

| User | Goal | Expected Experience |
|---|---|---|
| Python developer | Publish local functions such as `add()`, model inference, robot control, private data analysis | Write `@node.register` and `node.serve()`; EasyRemote prepares an already paired runtime, starts host, publishes capability. |
| Local developer | Try demos, debug agents, or run two local capabilities without team infrastructure | Explicitly choose a local dev Hub/runtime mode owned by EasyNet-Cli; no public listener by default. |
| Team operator | Start a Hub that devices can join | Use explicit CLI Hub lifecycle; CLI owns TLS, listener, state, realm, key/admission model. |
| Self-hosted private team | Manage users, devices, keys, grants, revocation, and audit without EasyNet Backend | Use the same Principal URA, public-key binding, key-service, admission, authorization, and receipt model exposed through CLI/API. |
| Product operator with Backend | Support login, organizations, device management, HTTP/browser surfaces, high-scale catalog operations | Backend maps product users to Principal URAs and submits complete Invocation through CLI daemon; it does not fork identity, daemon, signing, admission, or execution. |

---

## 1. Architectural Ownership

### 1.1 Ownership Table

| Concern | Owner | EasyRemote Role |
|---|---|---|
| Python authoring API: `ComputeNode`, `@node.register`, `Client`, `@remote` | EasyRemote | Own public Python facade and developer workflow. |
| Device runtime bootstrap sequencing for `node.serve()` | EasyRemote facade over SDK lifecycle | Sequence SDK check, identity projection, daemon reuse/start, warm host, ability deployment. |
| Daemon process lifecycle primitives | EasyNet-Cli SDK / libeasynet_cli | Provide canonical start/status/endpoint/transport/error semantics. |
| Identity projection, pairing, credentials, key material | EasyNet-Cli runtime / SDK | EasyRemote reads projection only; it never creates identity or changes realm. |
| Hub listener, TLS, config, Hub mode/both mode | EasyNet-Cli daemon lifecycle | EasyRemote may keep `Gateway` as a facade, but canonical behavior belongs in CLI SDK. |
| Invocation tuple, URA, signing, admission, receipts | EasyNet protocol/runtime through SDK | EasyRemote must not duplicate protocol semantics. |
| Backend account/org/device/product state | EasyNet Backend | Backend augments product UX and scale, but calls through daemon Invocation. |

### 1.2 Boundary Rules

1. EasyRemote may automatically start a **device daemon** only after a valid paired identity exists.
2. EasyRemote must not silently create a user, principal, device identity, realm, private key, or trust root.
3. `@node.register` must not start a daemon at import/decorator time. Decorators only register local Python function metadata and warm-host bindings.
4. `node.serve()` is the authoring lifecycle boundary. It may perform runtime bootstrap, start host, install abilities, print readiness, and block.
5. `Client()` may connect lazily to an existing daemon, but it must not silently create identity or launch a long-lived process unless a public API explicitly owns that lifecycle.
6. Hub mode must be explicit. A normal device publishing a function must not silently become the realm Hub.
7. Public behavior should remain compatible while internal ownership is cleaned up. `Gateway` can remain as a public facade while its internals migrate to CLI SDK ownership.

---

## 2. Use Case 1: First Local Function Publication

### 2.1 Target User Flow

Paired device:

```bash
python app.py
```

Expected console:

```text
✓ reused easynet-daemon for easynet:///r/acme/device/dev-a
✓ Published easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.add
```

If daemon is absent but identity exists:

```text
✓ started easynet-daemon for easynet:///r/acme/device/dev-a
✓ Published easynet:///r/acme/ability/system-agent.dev-a.ability-management.er.add
```

Unpaired device:

```text
No EasyNet identity found for this device.

To pair this device, run:
  easynet pair

Then restart this EasyRemote application.
```

### 2.2 Current State

Implemented in EasyRemote:

- `DeviceRuntimeBootstrap` sequences SDK feature check, identity projection, daemon availability probe, and device daemon start.
- `ComputeNode.start()` calls the runtime bootstrap before starting the warm host and deploying abilities.
- `ComputeNode.serve()` catches onboarding-required errors and prints an actionable pairing message instead of a runtime traceback.
- `@node.register` still only writes the ability package and registers the function in the host; it does not deploy before `start()`/`serve()`.

Implementation anchors:

- `easyremote/bootstrap.py`: explicit state machine.
- `easyremote/node.py`: authoring lifecycle and warm host deployment.
- `tests/test_bootstrap.py`, `tests/test_node.py`: facade-local contract coverage.

### 2.3 State Machine

```text
START
  -> SDK_READY
  -> IDENTITY_READY
  -> DAEMON_REUSED
  -> HOST_STARTED
  -> ABILITIES_DEPLOYED
  -> SERVING

START
  -> SDK_READY
  -> IDENTITY_READY
  -> DAEMON_STARTED
  -> HOST_STARTED
  -> ABILITIES_DEPLOYED
  -> SERVING

START
  -> SDK_READY
  -> IDENTITY_MISSING
  -> ONBOARDING_REQUIRED
  -> EXIT_WITH_PAIRING_INSTRUCTIONS
```

### 2.4 Failure Semantics

| Failure | Required Behavior |
|---|---|
| SDK ABI/environment unavailable | Raise typed EasyRemote error derived from SDK; do not start host. |
| Identity missing/corrupt/incomplete | Print `easynet pair` onboarding from `serve()`; raise `Unavailable(reason="onboarding_required")` from `start()`. |
| Daemon discovery file missing/offline | Start device daemon through SDK lifecycle. |
| Daemon discovery corrupt or incompatible | Do not mask by starting another daemon; surface the SDK-derived error. |
| Host start fails | Stop any daemon started by this bootstrap lease. |
| Ability deploy fails | Stop host and close owned daemon lease; rollback started state. |
| Late registration deploy fails | Remove the function from local host and ability map. |

### 2.5 Acceptance Criteria

1. A paired user can run the 12-line script with no explicit `LocalIdentity.load()` or `DaemonHandle.start_device(...)`.
2. An unpaired user sees exactly one clear next action: `easynet pair`.
3. `@node.register` remains side-effect-light: no daemon start, no network mutation, no identity creation.
4. `node.start()` remains usable for tests and non-blocking embedding; `node.serve()` is the blocking authoring entrypoint.
5. Unit tests cover both daemon reuse and daemon start branches.
6. A live E2E probe must separately verify register -> daemon deploy -> remote invoke against a real daemon. Facade-local tests do not claim full live closure.

---

## 3. Use Case 2: Personal Local Development

### 3.1 Target User Flow

The user wants to run demos or debug local agents without a team Hub:

```bash
easyremote dev init
python app.py
python client.py
```

Expected properties:

- Local realm only.
- Loopback by default.
- No public TCP listener unless explicitly requested.
- No default team authority root.
- Clear cleanup/reset command.

### 3.2 Current State

Not implemented as a closed product path.

Current EasyRemote can:

- Start/publish a device runtime after pairing.
- Start a Hub via `Gateway`/`easyremote hub`.

Current EasyRemote does not yet provide:

- A canonical local-only dev Hub mode.
- A local dev onboarding command that is clearly separate from team Hub operations.
- A CLI-owned lifecycle mode that prevents accidental public/team authority semantics.

### 3.3 Required CLI-Owned Mode

The local dev Hub must be implemented by EasyNet-Cli daemon lifecycle, not by a custom Python Hub in EasyRemote.

Required daemon/SDK properties:

```text
mode: local-dev-hub or equivalent explicit profile
realm: local deterministic or user-selected dev realm
listen: loopback by default
tls: daemon-owned policy
credentials: explicitly marked as local dev
catalog: local dev only
cleanup: canonical reset command
```

EasyRemote may expose a thin command only after CLI provides the canonical primitive:

```bash
easyremote dev init
easyremote dev status
easyremote dev reset
```

### 3.4 Non-Goals

- Do not silently turn `node.serve()` into local Hub creation.
- Do not make every device a Hub.
- Do not write long-lived team-like realm config for a throwaway local demo.
- Do not use EasyRemote `Gateway` internals as the canonical local dev Hub.

### 3.5 Acceptance Criteria

1. Local dev mode can run the hello node/client pair on one machine without an external Hub.
2. The mode is visibly local-only in status and console output.
3. It does not bind public interfaces by default.
4. It uses CLI daemon lifecycle and identity primitives.
5. It can be reset without touching unrelated team pairing state.

---

## 4. Use Case 3: Team Hub and Multi-Device Collaboration

### 4.1 Target User Flow

Team operator:

```bash
easynet hub start --realm my-team
```

or, while the EasyRemote facade remains public:

```bash
easyremote hub --realm my-team
```

Device operator:

```bash
easynet pair
python app.py
```

Caller:

```python
from easyremote import Client

gpu = Client().device("gpu-2")

@gpu.remote
def infer(prompt: str) -> str: ...

print(infer("hello"))
```

### 4.2 Correct Structure

```text
EasyRemote authoring facade
  -> easynet-sdk
  -> EasyNet-Cli daemon (device / hub / both)
  -> EasyNet Invocation + receipt runtime
```

Hub is the realm coordination, directory, admission, and routing authority. It is not a Python web server owned by EasyRemote.

### 4.3 Current State

Implemented:

- `Gateway`/`Server` public facade exists.
- `easyremote hub` starts a daemon in Hub mode through `DaemonHandle.start`.
- `Gateway` provisions self-signed TLS material, writes minimal Hub config if absent, and prints pairing guidance.

Architectural debt:

- `Gateway` still owns Hub provisioning logic that belongs in EasyNet-Cli SDK/daemon lifecycle: TLS material generation policy, Hub config materialization, and listener config shape.
- Public docs expose `Gateway` as an EasyRemote facade, so direct API deletion would be a breaking product change.

### 4.4 Required Migration

The target is not "delete the public `Gateway` name first." The target is:

1. EasyNet-Cli SDK exposes canonical Hub lifecycle/provisioning:

   ```text
   start_hub(config)
   ensure_hub_config(config)
   resolve_tls(config)
   pairing_guidance(handle)
   status(handle)
   ```

2. EasyRemote keeps public compatibility:

   ```python
   Gateway(realm="my-team").start()
   ```

   but delegates all provisioning and lifecycle decisions to the CLI SDK.

3. EasyRemote removes internal duplicated Hub config/TLS generation once SDK primitives exist.

4. If a future SPEC removes `Gateway`, provide explicit migration and deprecation. Do not remove it only because internals moved.

### 4.5 Acceptance Criteria

1. Hub startup behavior is identical through `easynet` CLI and EasyRemote facade.
2. TLS and listener policy are single-sourced in EasyNet-Cli.
3. Operator-authored config preservation remains guaranteed.
4. `easyremote hub` is a wrapper over canonical SDK behavior, not a second Hub implementation.
5. Multi-device register/discover/call E2E is verified against a real Hub.

---

## 5. Use Case 4: Self-Hosted Team Without Backend

### 5.1 Target User Flow

Private/self-hosted teams need governance without adopting a central Backend:

```text
admin creates principal
-> binds first public key
-> invites user/device
-> user adds second device/key
-> admin grants ability access
-> user invokes ability
-> receipts record authority and execution
-> key rotates/revokes
-> principal can be suspended/deleted
```

### 5.2 Required Concepts

| Concept | Meaning |
|---|---|
| Principal URA | Stable governed subject representing user/service/team actor. |
| Public-key binding | One principal may have one or more authorized public keys/devices. |
| Key-service custody | Optional private-key custody/recovery path, owned by EasyNet runtime/backend design, not EasyRemote. |
| Admission | Daemon/runtime decision to accept or reject an Invocation. |
| Authorization grant | Predicate allowing a principal/caller to advertise or invoke an ability. |
| Receipt | Verifiable execution/admission fact binding invocation, authority, input, output, and causal context. |

### 5.3 Required State Machines

Principal:

```text
INVITED
  -> ACTIVE
  -> SUSPENDED
  -> ACTIVE
  -> DELETED

ACTIVE
  -> RECOVERY_PENDING
  -> ACTIVE
```

Key binding:

```text
PENDING
  -> ACTIVE
  -> ROTATING
  -> REVOKED

ACTIVE
  -> COMPROMISED
  -> REVOKED
```

Authorization grant:

```text
DRAFT
  -> ACTIVE
  -> SUSPENDED
  -> ACTIVE
  -> REVOKED
  -> EXPIRED
```

Device membership:

```text
PENDING_PAIRING
  -> PAIRED
  -> TRUSTED
  -> SUSPENDED
  -> REMOVED
```

### 5.4 EasyRemote Role

EasyRemote should not implement these governance state machines.

EasyRemote may expose Python convenience readers/wrappers only after CLI/SDK owns the canonical operations, for example:

```python
Client().principals.list()
Client().grants.list()
```

These must be thin daemon Invocation facades, not local Python registries.

### 5.5 Acceptance Criteria

1. A self-hosted Hub can create/manage principals without a Backend.
2. A principal can have multiple device/key bindings.
3. Key rotation and revocation affect admission deterministically.
4. Ability advertisement and invocation permissions are separately governed.
5. Receipts contain enough authority evidence to audit who invoked what under which grant.
6. EasyRemote remains a capability authoring/calling facade and does not own governance storage.

---

## 6. Use Case 5: Backend-Backed Product at Scale

### 6.1 Backend Value

Backend exists to provide product capabilities that local daemon/Hubs should not own globally:

- PostgreSQL-backed accounts, organizations, devices, teams, and search.
- OAuth/browser login and session UX.
- HTTP APIs and dashboards.
- High-concurrency catalog queries.
- Product operations, billing, analytics, notifications, and administration.

### 6.2 Backend Must Not Reimplement

Backend must not create a second model for:

- Private-key management.
- Daemon process ownership.
- Device ability execution.
- Invocation signing and receipt semantics.
- Admission and authorization truth.
- Principal identity independent from Principal URA.

### 6.3 Required Integration Shape

```text
browser/frontend
  -> EasyNet Backend
  -> colocated or reachable easynet-daemon
  -> complete Invocation
  -> local or remote device/agent/hub ability
  -> receipt
```

Backend maps product users to Principal URAs:

```text
ProductUser(id=123, org=acme)
  -> Principal URA
  -> authorized public-key/device bindings
  -> grants
  -> daemon Invocation
```

### 6.4 Acceptance Criteria

1. Backend login maps to the same Principal URA used by CLI/Hubs.
2. Backend-submitted calls go through daemon Invocation, not direct device RPC.
3. Backend can query and render receipts but does not invent receipt semantics.
4. Backend device dashboards reflect daemon/Hub truth rather than replacing it.
5. Product-scale catalog search does not fork ability identity or governance.

---

## 7. Public API and Compatibility

### 7.1 Stable Public Authoring API

These remain the primary EasyRemote authoring/calling surfaces:

```python
ComputeNode()
@node.register
node.start()
node.serve()
Client()
@remote
client.device(...).remote
client.agent(...).remote
client.hub().call(...)
```

### 7.2 Lifecycle Facades

`DaemonHandle` remains a low-level explicit lifecycle handle for tests, embedding, and operators:

```python
DaemonHandle.start_device("dev-a")
DaemonHandle.start_hub("my-team")
```

Normal function authors should not need it.

### 7.3 Gateway Compatibility

`Gateway` and `Server` currently remain public.

Migration policy:

1. Preserve public behavior while removing internal duplicated ownership.
2. Move TLS/config/listener provisioning to EasyNet-Cli SDK.
3. Keep EasyRemote `Gateway` as a thin facade unless a future SPEC explicitly removes it.
4. Do not keep internal compatibility layers whose only purpose is preserving old architecture after the SDK owns the behavior.

---

## 8. Roadmap

### P0: Paired Developer Auto Runtime Bootstrap

Status: implemented in EasyRemote facade.

Scope:

- SDK check.
- Runtime identity projection.
- Daemon reuse/start.
- Host start.
- Ability deployment.
- Pairing onboarding message.

Remaining:

- Real daemon register -> invoke E2E should be part of release validation where environment permits.

### P1: Local Dev Hub

Status: not implemented.

Required first:

- CLI-owned local dev Hub/runtime profile.
- Clear loopback/local-only semantics.
- Reset/status commands.

EasyRemote after CLI primitive:

- Optional `easyremote dev ...` thin wrapper.
- Docs/examples for single-machine demos.

### P2: Hub Lifecycle Convergence

Status: public facade exists; internals still own provisioning details.

Required:

- CLI SDK canonical Hub provisioning and pairing guidance.
- EasyRemote `Gateway` delegates.
- Remove EasyRemote-owned TLS/config generation once CLI SDK covers it.

### P3: Self-Hosted Governance State Machines

Status: not closed in EasyRemote; belongs below EasyRemote.

Required:

- Principal, key binding, grant, device membership state machines.
- CLI/API operations and daemon admission effects.
- Receipt authority evidence.

### P4: Backend Integration

Status: product architecture target.

Required:

- Product user -> Principal URA mapping.
- Backend -> daemon Invocation submission.
- Receipt query/render path.
- Catalog scale path that preserves ability identity.

### P5: Two Real E2E Suites

Required E2E 1: no Backend, self-hosted Hub.

```text
start Hub
pair two devices
publish ability
discover ability
invoke ability
rotate/revoke key
observe admission change
inspect receipt
```

Required E2E 2: Backend-backed flow.

```text
login product user
map to Principal URA
pair/register device
publish ability
invoke via Backend through daemon
render receipt/audit trail
```

---

## 9. Test Strategy

### 9.1 Unit and Contract Tests

EasyRemote owns:

- Bootstrap state sequencing.
- Onboarding error conversion.
- ComputeNode host/deploy rollback.
- `Gateway` facade compatibility while it exists.
- Public Python API behavior.

### 9.2 Live Daemon Integration

Release validation should include:

- SDK feature negotiation.
- Runtime identity projection.
- Daemon reuse/start.
- Ability deploy.
- Remote `Client.call()` against published ability.
- Host stream frames for unary and generator functions.

### 9.3 Multi-Process / Multi-Device E2E

Required before claiming team collaboration closure:

- Hub process.
- Two device processes.
- Registration from one device.
- Discovery and invocation from another.
- Receipt and admission checks.

---

## 10. Non-Goals

1. EasyRemote will not create identities or keys.
2. EasyRemote will not become a Hub implementation.
3. EasyRemote will not own team governance storage.
4. EasyRemote will not implement Backend account/OAuth/product database state.
5. EasyRemote will not add a second Invocation, signing, URA, admission, or receipt model.
6. EasyRemote will not preserve obsolete internal architecture after CLI SDK owns the canonical behavior.

---

## 11. Summary

EasyRemote owns the Python developer experience for publishing and calling capabilities.

EasyNet-Cli owns the daemon runtime, Hub lifecycle, identity projection, local/remote routing, key/admission behavior, and canonical lifecycle APIs.

EasyNet Backend, when present, owns product-scale account and operations UX while mapping to the same Principal URA and daemon Invocation model.

Current completed work is Use Case 1's paired-device auto runtime bootstrap in the EasyRemote facade. The remaining work is not another decorator feature; it is closing the local dev, Hub lifecycle, self-hosted governance, Backend mapping, and live E2E product paths without forking runtime ownership.
