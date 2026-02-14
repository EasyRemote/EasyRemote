# EasyRemote: AI-Native Distributed Computing Framework — Building EasyNet

<div align="center">

![EasyRemote Logo](docs/easyremote-logo.png)

[![PyPI version](https://badge.fury.io/py/easyremote.svg)](https://badge.fury.io/py/easyremote)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/pypi/pyversions/easyremote)]()

> **"Torchrun for the World"**: Enabling any terminal user to mobilize global computing resources with a single command to execute local code.

**AI-Native Distributed Computing | Building the Next-Generation Computing Internet - EasyNet**

English | [中文](README_zh.md)

</div>

---

## From Private Functions to Global Computing Orchestration Engine

**EasyRemote is not just a Private Function-as-a-Service (Private FaaS) platform—it's our answer to the future of computing:**

> While current cloud computing models are platform-centric, requiring data and code to "go to the cloud" to exchange resources, we believe:
> **The next-generation computing network should be terminal-centric, language-interfaced, function-granular, and trust-bounded**.

We call it: **"EasyNet"**.

### Core Philosophy: Code as Resource, Device as Node, Execution as Collaboration

EasyRemote is the first-stage implementation of EasyNet, allowing you to:

* **🧠 Define task logic using familiar Python function structures**
* **🔒 Deploy computing nodes on any device while maintaining privacy, performance, and control**
* **🌐 Transform local functions into globally accessible task interfaces through lightweight VPS gateways**
* **🚀 Launch tasks as simply as using `torchrun`, automatically scheduling to the most suitable resources for execution**

### 💡 Our Paradigm Shift

| Traditional Cloud Computing | **EasyNet Mode**                       |
| --------------------------- | -------------------------------------------- |
| Platform-centric            | **Terminal-centric**                   |
| Code must go to cloud       | **Code stays on your device**          |
| Pay for computing power     | **Contribute to earn computing power** |
| Vendor lock-in              | **Decentralized collaboration**        |
| Cold start delays           | **Always warm**                        |

---

## 🔭 Current Implementation: Private Function-as-a-Service

### **Quick Experience: Join EasyNet with 12 Lines of Code**

```python
# 1. Start gateway node (any VPS)
from easyremote import Server
Server(port=8080).start()

# 2. Contribute computing node (your device)
from easyremote import ComputeNode
node = ComputeNode("your-gateway:8080")

@node.register
def ai_inference(prompt):
    return your_local_model.generate(prompt)  # Runs on your GPU

node.serve()

# 3. Global computing access (anywhere)
from easyremote import Client
result = Client("your-gateway:8080").execute("ai_inference", "Hello AI")
```

**🎉 Your device has joined EasyNet!**

### **🆚 Comparison with Traditional Cloud Services**

| Feature                        | AWS Lambda                                | Google Cloud             | **EasyNet Node**                  |
| ------------------------------ | ----------------------------------------- | ------------------------ | ---------------------------------------- |
| **Computing Location**   | Cloud servers                             | Cloud servers            | **Your device**                    |
| **Data Privacy**         | Upload to cloud                           | Upload to cloud          | **Never leaves local**             |
| **Computing Cost**       | $200+/million calls                       | $200+/million calls      | **$5 gateway fee**                 |
| **Hardware Limitations** | Cloud specs                               | Cloud specs              | **Your GPU/CPU**                   |
| **Startup Latency**      | 100-1000ms                                | 100-1000ms               | **0ms (always online)**            |
| **AI Agent Integration** | Custom API wrappers                       | Custom API wrappers      | **Native MCP/A2A protocols**       |

---

## 🤖 AI-Native Scenarios: What Problems Does EasyRemote Solve?

EasyRemote is purpose-built for the AI era. Beyond general distributed computing, it directly addresses the pain points AI teams face today:

- **GPU Isolation**: Team GPUs sit idle 80% of the time, yet cloud inference costs $200+/million calls
- **Data Can't Leave**: Healthcare, finance, and government data must stay on-premise, but AI models live in the cloud
- **Agent Integration Is Fragmented**: Connecting AI agents to real tools requires custom glue code for every service
- **Cold Starts Kill UX**: Cloud functions take 100-1000ms to wake up, destroying real-time AI experiences

### Deployable Now

| # | Scenario | Who It's For | What It Solves |
|---|----------|-------------|----------------|
| K1 | **Private AI Inference Hub** (Team GPU Pool) | AI teams / R&D groups | Share team GPUs for model inference with load balancing; eliminate redundant cloud spend |
| K2 | **Agent Tool Gateway** (Enterprise Tool Mesh) | Agent platform teams | Unified MCP/A2A tool catalog so Claude, GPT, and custom agents can discover and call enterprise functions |
| K3 | **A2A Operations Network** (Incident Copilot) | Platform SRE / Ops | Automated incident response via agent-to-agent task chains; reduce manual handoffs |
| K4 | **Demo-as-Service** (Demo-API) | Product / Pre-sales / Startups | Publish AI demos as callable APIs in 3 steps; rapid prototyping for investor demos and POCs |
| K5 | **Function Marketplace** (Org-Internal) | Platform / Middle-office teams | Reusable AI function registry with capability discovery and automatic load balancing |
| K6 | **Local Data Residency AI** | Healthcare / Finance / Government | Run AI inference locally on HIPAA/GDPR-compliant devices; data never leaves your network |
| K9 | **Runtime Device Capability Injection** | ToC Agent apps / Edge platforms | Dynamically inject camera/media/sensor skills onto user devices at runtime without restart |

### Roadmap

| # | Scenario | What's Needed |
|---|----------|--------------|
| K7 | **Multi-Agent Collaboration Factory** | A2A state machine enhancements for long-running task lifecycles |
| K8 | **MCP Resource Knowledge Network** | MCP resources/prompts extensions for full knowledge graph integration |

### Protocol Support for AI Agents

EasyRemote speaks the languages AI agents already understand — **MCP** and **A2A**:

**MCP (Model Context Protocol)** — AI agents (Claude, etc.) discover and invoke your functions as tools:

```python
# Your compute node registers functions as usual
@node.register(description="Summarize text using local LLM")
def summarize(text: str) -> str:
    return local_llm.summarize(text)

# Agents discover via MCP:  POST /mcp {"method": "tools/list"}
# Agents invoke via MCP:    POST /mcp {"method": "tools/call", "params": {"name": "summarize", ...}}
```

Supported: `initialize`, `tools/list`, `tools/call`, `ping`, batch requests, notifications, JSON-RPC 2.0

**A2A (Agent-to-Agent Protocol)** — Agents coordinate through standardized task execution:

```python
# Agent discovers:  POST /a2a {"method": "agent.capabilities"}
# Agent executes:   POST /a2a {"method": "task.execute", "params": {"task": {...}}}
# Agent notifies:   POST /a2a {"method": "task.send", "params": {...}}
```

Supported: `agent.capabilities`, `task.execute`, `task.send`, `ping`, task ID fallback, batch requests

**EasyRemoteClientRuntime** — Agent-side proxy that bridges MCP/A2A to EasyRemote's distributed gateway:

```python
from easyremote.protocols import EasyRemoteClientRuntime
runtime = EasyRemoteClientRuntime(gateway="your-gateway:8080")
# Exposes real gateway functions as MCP tools / A2A capabilities
# Supports node_id targeting, load_balancing, and streaming
```

### Two Developer Routes

| Route | For | How |
|-------|-----|-----|
| **Route A: Agent (MCP/A2A)** | AI agent platforms | `AI Agent --MCP/A2A JSON-RPC--> Protocol Gateway --gRPC--> Compute Nodes` |
| **Route B: Human (Decorator)** | Python engineers | `@node.register` to expose, `@remote` to call, transparent remote execution |

---

## 📚 Complete Documentation Guide

### 🌐 Multilingual Documentation

#### 🇺🇸 English Documentation

- **[📖 English Documentation Center](docs/en/README.md)** - Complete English documentation navigation

#### 🇨🇳 Chinese Documentation

- **[📖 中文文档中心](docs/zh/README.md)** - Complete Chinese documentation navigation

### Quick Start

- **[5-Minute Quick Start](docs/en/user-guide/quick-start.md)** - Fastest way to get started | [中文](docs/zh/user-guide/quick-start.md)
- **[Installation Guide](docs/en/user-guide/installation.md)** - Detailed installation instructions | [中文](docs/zh/user-guide/installation.md)

### 📖 User Guide

- **[Examples](docs/en/user-guide/examples.md)** - Core runnable examples | [中文](docs/zh/user-guide/examples.md)
- **[Business Use Cases & Route Layers](docs/zh/CORE_USE_CASES_AND_ROUTES.md)** - Current vs roadmap (MCP/A2A and decorator paths)
- **[Killer Apps Gallery](gallery/README.md)** - Real-world use-case catalog with flagship applications
- **[Gallery Projects](gallery/projects/README.md)** - Quickstart project templates restored from removed demos

### 🏗️ Protocol Deep Dive

- **[MCP Implemented Scope](docs/ai/mcp-integration.md)** - Current protocol behavior and limits
- **[A2A Implemented Scope](docs/ai/a2a-integration.md)** - Current protocol behavior and limits
- **Agent-side Gateway Proxy Runtime** - `EasyRemoteClientRuntime` (see MCP/A2A guides section 2.3)
- **[Capability Management Protocol (CMP)](docs/CAPABILITY_MANAGEMENT_PROTOCOL.md)** - Skill/ability CRUD on user nodes (install/uninstall/list)

### 🔬 Research Materials

- **[Technical Whitepaper](docs/en/research/whitepaper.md)** - EasyNet theoretical foundation | [中文](docs/zh/research/whitepaper.md)
- **[Research Proposal](docs/en/research/research-proposal.md)** - Academic research plan | [中文](docs/zh/research/research-proposal.md)
- **[Project Pitch](docs/en/research/pitch.md)** - Business plan overview | [中文](docs/zh/research/pitch.md)

---

## 🌟 Three Major Breakthroughs of EasyNet

### **1. 🔒 Privacy-First Architecture**

```python
@node.register
def medical_diagnosis(scan_data):
    # Medical data never leaves your HIPAA-compliant device
    # But diagnostic services can be securely accessed globally
    return your_private_ai_model.diagnose(scan_data)
```

### **2. 💰 Economic Model Reconstruction**

- **Traditional Cloud Services**: Pay-per-use, costs increase exponentially with scale
- **EasyNet Model**: Contribute computing power to earn credits, use credits to call others' computing power
- **Gateway Cost**: $5/month vs traditional cloud $200+/million calls

### **3. Consumer Devices Participating in Global AI**

```python
# Your gaming PC can provide AI inference services globally
@node.register
def image_generation(prompt):
    return your_stable_diffusion.generate(prompt)

# Your MacBook can participate in distributed training
@node.register  
def gradient_computation(batch_data):
    return your_local_model.compute_gradients(batch_data)
```

---

## Three-Paradigm Evolution: Computing Revolution Through Paradigmatic Leaps

> **"Computing Evolution is not linear progression, but paradigmatic leaps"**

### *Paradigm 1: FDCN (Function-Driven Compute Network)*

**Core Innovation**: From local calls → cross-node function calls
**Technical Expression**: `@remote` decorator for transparent distributed execution
**Paradigm Analogy**: RPC → gRPC → **EasyRemote** (spatial decoupling of function calls)

```python
# Traditional local calls
def ai_inference(data): return model.predict(data)

# EasyRemote: Function calls across global networks
@node.register  
def ai_inference(data): return model.predict(data)
result = client.execute("global_node.ai_inference", data)
```

**Breakthrough Metrics**:

- API Simplicity: 25+ lines → **12 lines** (-52%)
- Startup Latency: 100-1000ms → **0ms** (-100%)
- Privacy Protection: Data to cloud → **Never leaves local**

### **Paradigm 2: Intelligence-Linked Scheduling**

**Core Innovation**: From explicit scheduling → adaptive intelligent scheduling
**Technical Expression**: Intent-driven multi-objective optimization scheduling
**Paradigm Analogy**: Kubernetes → Ray → **EasyRemote ComputePool**

```python
# Traditional explicit scheduling
client.execute("specific_node.specific_function", data)

# EasyRemote: Intelligent intent scheduling
result = await compute_pool.execute_optimized(
    task_intent="image_classification",
    requirements=TaskRequirements(accuracy=">95%", cost="<$5")
)
# System automatically: task analysis → resource matching → optimal scheduling
```

**Breakthrough Metrics**:

- Scheduling Efficiency: Manual config → **Millisecond auto-decisions**
- Resource Utilization: 60% → **85%** (+42%)
- Cognitive Load: Complex config → **Intent expression**

### **Paradigm 3: Intent-Graph Execution**

**Core Innovation**: From calling functions → expressing intentions
**Technical Expression**: Natural language-driven expert collaboration networks
**Paradigm Analogy**: LangChain → AutoGPT → **EasyRemote Intent Engine**

```python
# Traditional function call mindset
await compute_pool.execute_optimized(function="train_classifier", ...)

# EasyRemote: Natural language intent expression
result = await easynet.fulfill_intent(
    "Train a medical imaging AI with >90% accuracy for under $10"
)
# System automatically: intent understanding → task decomposition → expert discovery → collaborative execution
```

**Breakthrough Metrics**:

- User Barrier: Python developers → **General users** (10M+ user scale)
- Interaction Mode: Code calls → **Natural language**
- Collaboration Depth: Tool calls → **Intelligent agent networks**

### **🔄 Paradigm Spiral: Vertical Evolution Roadmap**

```
┌────────────────────────────────────────────────────────────┐
│                 Global Compute OS                          │ ← Paradigm 3: Intent Layer
│    "Train medical AI" → Auto-coordinate global experts     │   (Intent-Graph)
└────────────────────────────────────────────────────────────┘
                            ▲
┌────────────────────────────────────────────────────────────┐
│              Compute Sharing Platform                      │ ← Paradigm 2: Autonomous Layer  
│    Intelligent scheduling + Multi-objective optimization   │   (Intelligence-Linked)
└────────────────────────────────────────────────────────────┘
                            ▲
┌────────────────────────────────────────────────────────────┐
│               Private Function Network                      │ ← Paradigm 1: Function Layer
│    @remote decorator + Cross-node calls + Load balancing   │   (Function-Driven)  
└────────────────────────────────────────────────────────────┘
```

**Ultimate Vision**: Mobilize global computing as easily as using `torchrun`

```bash
$ easynet "Train a medical imaging AI with my local data, 95%+ accuracy required"
🤖 Understanding your needs, coordinating global medical AI expert nodes...
✅ Found stanford-medical-ai and 3 other expert nodes, starting collaborative training...
```

---

## 🔬 Technical Architecture: Decentralization + Edge Computing

### **Network Topology**

```
🤖 AI Agents (MCP/A2A)    🌍 Human Clients (Decorator/@remote)
         \                      /
          v                    v
   ☁️ Lightweight gateway cluster (routing + protocol adaptation, no computing)
                    ↓
        💻 Personal computing nodes (actual GPU/CPU execution)
                    ↓
           🔗 Peer-to-peer collaboration network
```

### **Core Technology Stack**

- **Communication Protocol**: gRPC + Protocol Buffers
- **Secure Transport**: End-to-end encryption
- **Load Balancing**: Intelligent resource awareness
- **Fault Tolerance**: Automatic retry and recovery

---

## 🌊 Join the Computing Revolution

### **🔥 Why EasyNet Will Change Everything**

**Limitations of Traditional Models**:

- 💸 Cloud service costs grow exponentially with scale
- 🔒 Data must be uploaded to third-party servers
- ⚡ Cold starts and network latency limit performance
- 🏢 Locked into major cloud service providers

**EasyNet's Breakthroughs**:

- 💰 **Computing Sharing Economy**: Contribute idle resources, gain global computing power
- 🔐 **Privacy by Design**: Data never leaves your device
- 🌐 **Decentralized**: No single points of failure, no vendor lock-in

### **Our Mission**

> **Redefining the future of computing**: From a few cloud providers monopolizing computing power to every device being part of the computing network.

### **Join Now**

```bash
# Become an early node in EasyNet
pip install easyremote

# Contribute your computing power
python -c "
from easyremote import ComputeNode
node = ComputeNode('demo.easynet.io:8080')
@node.register
def hello_world(): return 'Hello from my device!'
node.serve()
"
```

---

## 🏗️ Developer Ecosystem

| Role                             | Contribution                           | Benefits                         |
| -------------------------------- | -------------------------------------- | -------------------------------- |
| **Computing Providers**    | Idle GPU/CPU time                      | Computing credits/token rewards  |
| **Application Developers** | Innovative algorithms and applications | Global computing resource access |
| **Gateway Operators**      | Network infrastructure                 | Routing fee sharing              |
| **Ecosystem Builders**     | Tools and documentation                | Community governance rights      |

---

## Join the Community

* **Technical Discussions**: [GitHub Issues](https://github.com/Qingbolan/EasyCompute/issues)
* **Community Chat**: [GitHub Discussions](https://github.com/Qingbolan/EasyCompute/discussions)
* **Business Collaboration**: [silan.hu@u.nus.edu](mailto:silan.hu@u.nus.edu)
* **Project Founder**: [Silan Hu](https://github.com/Qingbolan) - NUS PhD Candidate

---

<div align="center">

## 🌟 "The future of software isn't deployed on the cloud, but runs on your system + EasyNet"

**Ready to join the computing revolution?**

```bash
pip install easyremote
```

**Don't just see it as a distributed function tool — it's a prototype running on old-world tracks but heading towards a new-world destination.**

*⭐ If you believe in this new worldview, please give us a star!*

</div>
