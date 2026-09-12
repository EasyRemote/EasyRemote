# 你写的是一个函数，世界向你要的却是一个服务

<div align="center">

![EasyRemote Logo](docs/easyremote-logo.png)

[![PyPI version](https://badge.fury.io/py/easyremote.svg)](https://badge.fury.io/py/easyremote)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/pypi/pyversions/easyremote)]()

> **EasyRemote 把本地函数变成一个受治理、可由通过准入的 EasyNet 用户、Agent 与设备调用的 Ability。**

**EasyNet 原生 · 签名调用 · 可验证执行**

[English](README.md) | 中文

</div>

---

你本地有个能力——一个模型、一段 pipeline、一个查库函数。同事想用，agent 想调，别的项目想接。今天的答案是同一套仪式：打包、容器、部署、鉴权、维护。**分享的最小单位是"一次部署"——所以绝大多数能力，从来没被分享过。**

为什么非部署不可？因为你的机器藏在 NAT 后面，世界够不着它。一块 4090 在你桌底吃灰，不是它不够强——放在十年前它是超算——是它没有任何安全地被调用的方式。上传，是过去唯一的出路。

EasyRemote 把分享的最小单位降到一个函数：

```python
from easyremote import ComputeNode

node = ComputeNode()

@node.register
def ai_inference(prompt: str) -> str:
    return model.generate(prompt)   # 跑在你的 GPU 上，模型常驻内存

node.serve()
```

注册之后，这个函数成为一个 **capability**。capability 不是修辞，它有最小定义——**可调用、可发现、可组合**，三者同时成立：

```python
# 同事：像调本地函数
from easyremote import Client, FreshRoot, ResolvedTargetSubject
client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))
client.execute("ai_inference", prompt="hello")

# Agent runtime：通过 EasyRemote client 调同一个能力
#   client.call("ai_inference", prompt="hello")

# 系统：作为 Pipeline 的一步，和别人的函数编排成任务链
from easyremote import Pipeline
pipe = Pipeline("nightly")
fetch = pipe.step("teamA.fetch_sales", quarter="Q2")
pipe.step("er.summarize", rows=fetch.output)
```

这不是三个不同产品，而是同一个受治理 Ability 的三种使用方式。代码和模型留在你的机器上；通过授权的调用者拿到接口调用权，而不是实现副本。

Git 把分享代码的单位从项目降到一次 commit。Docker 把部署软件的单位从一台机器降到一个镜像。**EasyRemote 把共享服务的单位，从一次 deployment 降到一个函数。**

**第一个直接的推论：团队 GPU 池。** 函数留在设备上执行，办公室、家里或宿舍的 GPU 可以组成一个受治理的推理入口。设备向 Hub 发起出站连接，模型可以保持常驻；实际可达性、启动时间、延迟和成本仍取决于部署。

**你大概会问：让别人调用自己的机器，不危险吗？** 这正是过去没人敢做这件事的原因。EasyRemote 构建在 EasyNet 栈上：签名 Invocation 记录谁调用、调用谁、作用于什么对象，以及它属于哪条因果链；签名路径以可验证 Receipt 事实闭合。应用代码不用自行构造这些对象，但 operator 仍需配置身份、配对、policy 与生命周期，EasyRemote 不会绕过这些决定。

**而它真正不可替代的时刻，是 agent 要操作真实世界资源的那天。** agent 的能力每三个月上一个台阶，问责方式却从未变过：一次 tool call 发出去，剩下全凭它自己汇报。让它查天气无所谓；让它动数据库、下采购单、操作设备——"它做了什么"不能再是自述。签名调用 + 回执链给出的授权语义是：**这个 agent、以我的授权、在这条任务链里、可以调这个能力、动这个对象**。

Ray、Modal、RunPod 把远程执行做**易**，工具协议让 agent 变得**可连接**；没有人把本地能力做成**可组合、可问责**的服务单元。我们做的是它们之间缺的那一层。

**云计算让代码迁移到计算资源。EasyRemote 让计算资源留在原地，并让受治理接口通过 EasyNet 被调用。**

EasyRemote 只拥有 Python ergonomics：schema 派生、`@node.register`、`@remote`、
Ability package 与常驻 Python host。EasyNet-Cli 拥有 `easynet-daemon`、配对、
密钥、路由、Provider 生命周期与 SDK transport；Axon 拥有 canonical Invocation、
admission、Receipt 与 stream terminal 语义。`node.serve()` 只启动 Python
Provider，不负责安装、配对或启动 daemon。

---

## 上手

当前源码预览依赖 `easynet-sdk>=0.162.9,<0.163`，该版本尚未出现在公共 package
registry。dependency-first 发布完成前，请把三个仓库保持为 sibling checkouts：

```text
workspace/
  EasyNet-Axon/
  EasyNet-Cli/
  EasyRemote/
```

```bash
cd EasyRemote
uv sync

cd ../EasyNet-Cli
packaging/release/dev-install-local.sh --debug

cd ../EasyRemote

# 一次性身份配置（为签名调用与回执链建立身份）。
# 使用 EasyNet-Cli 运维入口启动 device 或 Hub runtime。
# `node.serve()` 只连接该 operator-managed runtime。
easynet login
easynet device join <pairing-token>
easynet runtime start
easyremote doctor                            # 可选：逐项体检运行时
```

之后就是上面的 12 行。首次运行若未配对，`node.serve()` 不会伪造身份。先执行
`easynet login` 和 `easynet device join <pairing-token>`，再通过
`easynet runtime start` 启动或连接由 EasyNet operator 管理的 Runtime。Provider
会连接该 Runtime、启动 Python warm host，并发布全部已注册函数。配对提供 caller
identity 与签名；选择 device 只决定函数在哪里执行，不会向调用者开放整台机器。

`examples/` 提供可直接运行的 node/client 配对：

| Example | 展示内容 |
|---|---|
| `01_hello_node.py` / `02_hello_client.py` | 最小 register → call |
| `03_pipeline.py` | 将 abilities 编排为 EAL mission |
| `remote_demo_node.py` / `remote_demo_client.py` | `@node.register` + `@remote` 支持的完整函数形状 |
| `04_streaming_node.py` / `04_streaming_client.py` | 用逐帧到达间隔验证流是增量传输而非批量返回 |

### 生产用例

面向生产问题的最小 MVP 位于 [`gallery/projects/`](gallery/projects/)。它们不是
feature snippet，而是彼此独立的 uv 应用：

| Project | 最小任务 |
|---|---|
| [远程报价](gallery/projects/00_basic_remote_math/) | 共享一条经过校验的定价规则，而不先建设报价服务 |
| [常驻模型](gallery/projects/01_team_gpu_pool_load_balancing/) | 调用留在指定 GPU device 上的模型 |
| [企业工具边界](gallery/projects/02_mcp_tool_mesh/) | 给 Agent 类型化业务操作，而不是后端凭证 |
| [事故证据](gallery/projects/03_a2a_incident_copilot/) | 无需 SSH，对白名单服务诊断并流式返回有界证据 |
| [函数复用](gallery/projects/04_function_marketplace/) | 不复制源码，直接消费其他团队持有的业务逻辑 |
| [数据驻留 AI](gallery/projects/05_local_data_residency_ai/) | 原始记录留在本地，只释放有界投影 |
| [设备摄像头](gallery/projects/06_runtime_device_capability_injection/) | 不开放设备，流式读取有限媒体帧 |
| [机器人动作](gallery/projects/07_claude_code_robot_commander_mcp/) | 给 Agent 一项受约束、可归因的动作，而非机器控制权 |
| [网络原生库](gallery/projects/08_network_native_python_library/) | 安装本地类型接口，同时让 Provider 实现继续留在远端 |

每个项目都有自己的 `pyproject.toml`、`uv.lock`、provider、caller 和精炼的 case
paper；入口见 [Gallery index](gallery/projects/README.md)。

### 像调用 Python 函数一样调用

```python
from easyremote import Client, FreshRoot, ResolvedTargetSubject, remote

client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))

@remote(client=client)
def ai_inference(prompt: str) -> str: ...

print(ai_inference("hello"))
```

stub 与已发布函数具有相同名称和类型签名，但不复制它的实现。函数始终在
provider 所在设备执行。

### 选择执行设备

```python
gpu = client.device("gpu-2")

@gpu.remote
def ai_inference(prompt: str) -> str: ...

print(ai_inference("hello from this GPU"))
```

指定 paired device 只选择执行位置，不会暴露 SSH、端口、模型文件、数据库凭证或
底层设备 API。

### 多模态二进制流

yield `StreamFrame` 可以保留原始媒体 bytes 与 content type。同一个 `@remote`
stub 负责消费该流：JSON frame 仍是普通 Python 值，媒体 frame 则保持为
`StreamFrame`。

```python
from collections.abc import Iterator
from easyremote import ComputeNode, StreamFrame, remote

node = ComputeNode()

@node.register
def camera(frames: int) -> Iterator[StreamFrame]:
    for jpeg in capture_jpegs(frames):
        yield StreamFrame(jpeg, "image/jpeg")

@remote(client=client)
def camera(frames: int) -> Iterator[StreamFrame]: ...

for frame in camera.stream(30):
    consume(frame.payload, frame.content_type)
```

在本地 Provider host → `easynet-daemon` Unix-socket 边界，`binary_v1` 不经过
JSON 或 base64 转换，保留 `StreamFrame` 的 bytes 与 media type。网络路径仍由
Runtime 与 SDK 负责；这不是端到端 zero-copy、延迟或带宽承诺。JSON generator
使用同一个 `.stream(...)` 接口。

### Provider 生命周期

`ComputeNode` 把 readiness 表达成显式顺序：

```text
declared → schema → package → ability.deploy → Local active
         → realm advertisement pending/confirmed → lease renewal → stop/expiry
```

`Local active` 只表示 paired local daemon 可以调用 Provider，不证明 realm 已经可见。
在所属 Runtime/product 确认发布前，EasyRemote 只报告 advertisement pending。

---

## 项目状态

EasyRemote v2 当前处于 alpha 阶段，不兼容 v1。当前已经支持类型化同步与异步
函数、有限 server stream、本地精确 binary/media host frame、device targeting、
warm provider、caller context、签名 invocation receipt，以及 Receipt 锚定的
`Context.call` / `Context.invoke` / `Context.stream` 子调用。

使用 EasyRemote 需要已配对且正在运行的 EasyNet runtime。跨设备延迟和带宽取决于
实际部署，本 alpha 不宣称统一网络 SLO。request-side media streaming，以及完整
远端 receipt chain 的拉取与独立验证尚未完成。

详细架构说明见 [`v2 design`](docs/design/easyremote-v2-easynet-refactor.md)。

EasyRemote 是一个分阶段公开的更大研究系统中的 Python facade；
[Public Source Release Scope](SOURCE_RELEASE_SCOPE.md) 说明当前公开边界，但不改变本仓库
已经授予的 MIT 权利。

## 归属与引用

EasyRemote 使用 MIT 许可证。EasyNet 运行时依赖是 Apache-2.0 项目，见 [`NOTICE.md`](NOTICE.md)。用于定位设计的系统与研究参考文献集中列在 [`docs/REFERENCES.md`](docs/REFERENCES.md)。

## License

[MIT](LICENSE) © Silan Hu
