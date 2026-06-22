# EasyRemote Gallery

Author: Silan Hu (silan.hu@u.nus.edu)

## Purpose

`gallery/` is no longer a runnable example collection. The old implementations have been removed. This directory now keeps the product-level scenarios that explain why EasyRemote matters: who needs it, what concrete use case it serves, what is broken today, what idea EasyRemote is trying to establish, and what outcome the user should get.

Each entry follows the same structure:

- Usage scenario: where this happens in a team, organization, device fleet, or agent workflow.
- Concrete use case: one specific task a real user can understand immediately.
- Current problem: what blocks this workflow without EasyRemote.
- Intent: the capability model EasyRemote is trying to establish.
- Target outcome: what should become possible for the user.

For currently runnable code, see [`../examples/README.md`](../examples/README.md). The gallery explains why these capabilities are worth productizing.

## Overview

| ID | Scenario | Primary users | Core intent |
|---|---|---|---|
| K1 | Private AI Inference Hub | AI teams / R&D groups | Turn scattered team GPUs into callable shared inference capabilities |
| K2 | Agent Capability Backend | Agent platform teams | Give agents a unified, governable, auditable enterprise capability catalog |
| K3 | A2A Incident Copilot Network | Platform engineering / SRE | Turn incident actions into composable agent task chains |
| K4 | Demo-as-API | Product / sales engineering / startups | Let local prototypes become demoable interfaces at function granularity |
| K5 | Internal Function Marketplace | Platform teams / shared service teams | Turn repeated business functions into discoverable reusable capability assets |
| K6 | Local Data Residency AI | Healthcare / finance / government | Move computation to the data instead of moving sensitive data away |
| K7 | Long-Running Multi-Agent Factory | Agent workflow platforms | Give long multi-agent workflows state, receipts, and recoverability |
| K8 | MCP Resource Knowledge Network | Knowledge platforms / agent platforms | Extend tool calling into a governed network of tools, resources, and prompts |
| K9 | Runtime Device Capability Injection | Consumer agent apps / edge platforms | Install device capabilities on demand instead of preinstalling every capability |
| K10 | Claude Code Robot Commander | Agent products / robotics platforms | Let a commander skill remotely deploy and operate user-side device capabilities |

## K1 Private AI Inference Hub

### Usage Scenario

An AI team has multiple personal workstations, lab machines, or office GPU boxes. Each machine has different models, different VRAM, and different idle windows, but each machine is usually usable only by its owner.

### Concrete Use Case

Researcher A keeps an embedding model warm on a local RTX 4090. Researcher B needs to batch-generate embeddings for an evaluation script. B should not redeploy the model to the cloud, copy the data around, or ask A to hand-build an HTTP endpoint. A registers `embed_text` as an EasyRemote capability, and B calls it like a team service.

### Current Problem

Team GPU sharing usually collapses into three poor choices: redeploy the model to cloud infrastructure, ask a teammate to run scripts over SSH, or wrap every local model in an ad hoc HTTP service. The first is expensive, the second is ungoverned, and the third creates duplicated maintenance work with weak identity, routing, auditing, and load distribution.

### Intent

EasyRemote is not trying to be another GPU scheduler. The intent is to turn functions that already live on GPU machines into discoverable, callable, composable remote capabilities. The machine stays where it is, the model stays warm locally, and the team receives call rights rather than machine control.

### Target Outcome

Every team GPU can naturally join a shared inference pool. Idle compute gets used, models do not need duplicate deployments, calls can be routed to suitable nodes, and every invocation has identity and receipts. For the caller, this stops being "borrowing a machine" and becomes "calling a team capability."

## K2 Agent Capability Backend

### Usage Scenario

An enterprise has multiple agent runtimes: support agents, analytics agents, coding agents, and operations agents. Each agent needs to call enterprise functions, database queries, ticketing systems, internal models, and approval actions.

### Concrete Use Case

A sales analytics agent needs `query_crm_account`, `summarize_pipeline`, and `create_followup_task`. These functions are owned by the CRM team, the data team, and sales operations. EasyRemote exposes them as one capability catalog, and the agent runtime discovers and calls them through the same interface.

### Current Problem

Agent tool integration is often one-off glue code. One agent connects to one set of tools, each team writes its own wrapper, and authorization policy ends up scattered across services. It becomes unclear which tool is callable, who owns it, and what evidence exists after an agent uses it.

### Intent

EasyRemote shifts the agent backend from "each agent wires its own tools" to "the organization maintains a capability backend." Agents do not directly own business systems. They request capabilities through signed invocations, while the owning team keeps the function in its own environment.

### Target Outcome

The agent platform gets a stable enterprise tool mesh. Capabilities are enumerable, routable, and auditable. Business teams can publish functions independently, and agents can compose those functions without copying business logic. Tool integration moves from project-level glue to organization-level capability governance.

## K3 A2A Incident Copilot Network

### Usage Scenario

Platform engineers and SREs handle alerts, slow queries, restarts, capacity checks, and rollback decisions. A single incident usually requires switching across multiple systems, scripts, dashboards, and roles.

### Concrete Use Case

A database latency alert fires at 2 a.m. The incident copilot calls a log diagnosis node for recent errors, a metrics node for latency spikes, and a read-only deployment node for recent releases. If it identifies a configuration issue, it prepares a remediation plan and asks for human approval before executing any risky action.

### Current Problem

Operations automation is often blocked by the fact that scripts exist but cannot be safely orchestrated. Scripts live on different machines, credentials sit in personal environments, and an agent may be able to suggest an action without having a controlled way to execute it. After execution, there is often no trustworthy task chain that says who triggered what and what object was touched.

### Intent

EasyRemote turns operations actions into authorized capabilities. Each diagnostic or remediation step becomes a clear capability, and the A2A task chain organizes those capabilities into a traceable incident workflow.

### Target Outcome

SREs no longer have to manually shuttle context between terminals and dashboards. The incident copilot can perform low-risk diagnosis, collect evidence, and prepare recommendations, while high-risk changes keep a human approval point. Every call has identity, parameters, result, and receipt for review.

## K4 Demo-as-API

### Usage Scenario

Product teams, sales engineers, and startup teams often have a prototype that works locally: a model, a data processing function, a hardware script, or an internal pipeline. The problem is that it is not yet a service, so customers or teammates cannot try it directly.

### Concrete Use Case

A sales engineer has a local `summarize_contract_risk` function for a customer demo tomorrow. There is no time to deploy a backend, request a domain, configure a gateway, and write authentication. With EasyRemote, the function is registered as a capability, and the demo client calls that remote function live.

### Current Problem

Demos are often forced into either screen sharing or rushed temporary deployment. Screen sharing is not real integration, while temporary deployment consumes time on infrastructure rather than product validation. Many useful prototypes never reach real feedback because the service boundary is too expensive to create.

### Intent

EasyRemote lowers the minimum demo unit from a backend service to a local function. If the function runs, it can be called, validated, and composed first. Service hardening, scaling, and governance can follow after the demand is proven.

### Target Outcome

Teams can turn local capabilities into demoable, testable, integrable interfaces faster. Customers see a real callable capability instead of a recording or mock. Engineering teams avoid taking on full deployment debt before the idea has been validated.

## K5 Internal Function Marketplace

### Usage Scenario

An organization has many repeated functions: exchange-rate normalization, customer segmentation, log cleaning, ticket classification, report generation, and permission checks. They are scattered across repositories, scripts, and team services.

### Concrete Use Case

The operations team needs customer health scoring in a new workflow. The data team already owns this logic, but historically the operations team would copy code or request a new API. With EasyRemote, the data team registers `score_customer_health` as a capability, and the operations workflow discovers and calls it directly.

### Current Problem

Organizations repeatedly rebuild similar functions because existing capabilities are not discoverable, callable, or trustworthy. Even when someone knows another team has the logic, they still need to renegotiate the interface, permissions, deployment, and SLA. Function assets never become an organization-level catalog.

### Intent

EasyRemote defines a function marketplace as a catalog of callable capabilities, not a documentation page or a set of snippets. Function assets remain owned by their original teams, but enter the marketplace through common registration, discovery, invocation, and receipt semantics.

### Target Outcome

New projects can search and compose existing capabilities before writing new ones. Platform teams can govern tags, permissions, versions, audits, and quality signals around capabilities. Business functions move from private team scripts to organization-level assets.

## K6 Local Data Residency AI

### Usage Scenario

Healthcare, finance, government, and industrial teams want AI summarization, classification, retrieval, risk scoring, or anomaly detection, but raw data cannot freely leave the local network, device, or compliance boundary.

### Concrete Use Case

A hospital keeps patient notes on an internal server. An external analysis agent wants a sanitized case summary and risk labels, but must never read the raw note. The hospital node registers `summarize_patient_record`; the function reads the local record inside the hospital boundary and returns only the sanitized result.

### Current Problem

Many AI workflows assume that data can be uploaded to a cloud model or central service. In regulated environments, that step is often unacceptable. Fully local processing keeps data safe, but makes it hard to connect to remote agents, orchestration systems, and cross-system workflows.

### Intent

EasyRemote moves computation toward the data instead of moving the data toward computation. The remote system receives an invocation endpoint and an allowed result. Sensitive data, model weights, and local context remain inside the compliance boundary.

### Target Outcome

Organizations can include local AI processing in remote workflows without moving raw data. Callers receive structured results, while data owners retain execution environment, access policy, and audit evidence. AI becomes usable without abandoning data residency.

## K7 Long-Running Multi-Agent Factory

### Usage Scenario

Some tasks cannot be completed by a single tool call: research reports, batch migrations, long simulations, cross-system approvals, code repair, and verification. These workflows can run for minutes or hours and involve multiple agents and capabilities.

### Concrete Use Case

An engineering agent receives a task to fix a production performance regression. It must pull metrics, identify version differences, generate a patch, run tests, ask a reviewer agent to inspect it, and then let a deployment agent perform a staged rollout. Each step can fail, retry, pause, or wait for human approval.

### Current Problem

Many agent workflows still behave like synchronous function calls: send a request and wait for a result. Long tasks need partial results, cancellation, recovery, timeout handling, human intervention, and multi-agent handoff. When they fail, it is hard to know where the task stopped and which actions actually executed.

### Intent

EasyRemote's intent for this direction is to extend capability calls and receipt chains into long-task lifecycles. Multi-agent coordination should not be just a message stream. It should be a task factory made from explicit capabilities, state machines, authorization chains, and execution evidence.

### Target Outcome

Long workflows can be paused, resumed, observed, and audited. Multiple agents can cooperate around the same task context. The system can distinguish what was planned, what was executed, and which step needs a human decision. This moves agents from short tool calls toward managed production workflows.

## K8 MCP Resource Knowledge Network

### Usage Scenario

Enterprise agents need more than tool calls. They also need resources, prompts, domain knowledge, and organizational context: knowledge bases, design standards, runbooks, customer records, project templates, and internal prompts.

### Concrete Use Case

A support agent handles an enterprise escalation. It needs to read the customer's SLA, recent tickets, product documentation, and standard response template before calling an internal diagnosis tool. The tool call is only the final step; the resources and prompts before it must also be discoverable and governed.

### Current Problem

MCP makes tool connectivity clearer, but real enterprises maintain tools, resources, and prompts in different systems. Agents may get a tool without the right context, or receive documents without knowing which content is permitted for the current identity and task.

### Intent

EasyRemote's intent for this direction is to extend capability from function invocation into a knowledge capability network of tools, resources, and prompts. Tools act, resources provide context, prompts encode organizational practice, and all three need shared permission and invocation semantics.

### Target Outcome

Agents can find the right material before execution, call the right tools during execution, and follow organizational templates and permission boundaries in the output. Knowledge stops being scattered documentation and becomes a discoverable, composable, auditable workflow resource.

## K9 Runtime Device Capability Injection

### Usage Scenario

Consumer agent apps and edge platforms manage large fleets of user devices. Each device has different hardware, OS permissions, and available actions. The platform should not have to preinstall every future capability into every client.

### Concrete Use Case

A home assistant agent, after user approval, needs a phone to take a photo, record a short video, or sample audio. The client initially keeps only a safe installation entrypoint. When the task needs camera access, the server sends a camera skill payload to that user's device, the device registers a new local capability, and the agent calls it.

### Current Problem

Preinstalling every device capability increases app size, permission pressure, review friction, and attack surface. Waiting for a new release before adding capabilities slows agent product iteration. More importantly, device actions must be scoped by user, device, and authorization; they cannot become arbitrary platform remote control.

### Intent

EasyRemote turns device actions into runtime capabilities that can be installed on demand. The user device is not opened as a raw remote machine. It receives, registers, and executes a specific capability inside an authorization boundary.

### Target Outcome

Agent products can extend device actions when a task needs them, without requiring every client to ship every feature in advance. The user side retains confirmation and execution boundaries, while the platform can target nodes by `user:<id>` or device capability. Adding a device action becomes "install one authorized capability" rather than "ship a new client release."

## K10 Claude Code Robot Commander

### Usage Scenario

Developers or robotics platforms want a Claude Code commander skill to do more than write code and plans. It should use one controlled toolchain to deploy tasks, install runtime capabilities, operate user-side robots or sandbox devices, and read telemetry.

### Concrete Use Case

A developer installs `RobotCommanderSkill` in Claude Code. They ask, "Move demo-user's inspection robot forward by one meter and report status." The commander calls EasyRemote through MCP, locates that user's client-sandbox node, installs a robot runtime skill, deploys the task plan, executes the action, and pulls telemetry.

### Current Problem

Robot control is usually tied to vendor SDKs, local networks, and device-specific protocols. An agent may be able to generate a good plan but still lacks a safe cross-network path to user-side hardware. Turning Claude Code into a control entrypoint is risky without capability boundaries, user targeting, authorization granularity, and execution evidence.

### Intent

EasyRemote lets the commander express high-level intent while the capability layer handles remote deployment, runtime injection, node targeting, and invocation receipts. Claude Code does not directly take over a device. It calls user-authorized actions through a controlled capability chain.

### Target Outcome

Robotics platforms can package complex device operations as installable, callable, auditable capability bundles. The commander skill handles planning and orchestration, while the user node handles local execution and permission boundaries. Agents can operate real devices with explicit authorization and evidence at every step.
