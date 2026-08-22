# 你写的是一个函数，世界向你要的却是一个服务

<div align="center">

![EasyRemote Logo](docs/easyremote-logo.png)

[![PyPI version](https://badge.fury.io/py/easyremote.svg)](https://badge.fury.io/py/easyremote)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/pypi/pyversions/easyremote)]()

> **EasyRemote turns a local function into a globally callable capability.**

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

这不是三个使用场景——**这是 capability 这个抽象的全部语义**。代码和模型留在你的机器上，世界拿到的是调用权，不是副本。

Git 把分享代码的单位从项目降到一次 commit。Docker 把部署软件的单位从一台机器降到一个镜像。**EasyRemote 把共享服务的单位，从一次 deployment 降到一个函数。**

**第一个直接的推论：团队 GPU 池。** 当函数留在设备上执行，算力共享是副产品：办公室、家里、宿舍的显卡组成一个推理集群——节点只向外拨号，NAT 不是障碍；模型常驻显存，没有冷启动；网关是一台 $5 的 VPS。

**你大概会问：把自己的机器开放出去，不危险吗？** 这正是过去没人敢做这件事的原因。EasyRemote 构建在 EasyNet 栈上：每次调用是签名的调用对象——谁调的、调谁、动什么对象、跟在哪条因果链后——每次执行留下可验证的回执。**这一层没有开关、没有配置，你几乎不会意识到它存在**，但它是你敢把机器开放给团队的全部原因。

**而它真正不可替代的时刻，是 agent 要操作真实世界资源的那天。** agent 的能力每三个月上一个台阶，问责方式却从未变过：一次 tool call 发出去，剩下全凭它自己汇报。让它查天气无所谓；让它动数据库、下采购单、操作设备——"它做了什么"不能再是自述。签名调用 + 回执链给出的授权语义是：**这个 agent、以我的授权、在这条任务链里、可以调这个能力、动这个对象**。

Ray、Modal、RunPod 把远程执行做**易**，工具协议让 agent 变得**可连接**；没有人把本地能力做成**可组合、可问责**的服务单元。我们做的是它们之间缺的那一层。

**云计算让代码迁移到计算资源。EasyRemote 让计算资源留在原地，同时获得全球可调用性。**

---

## 上手

```bash
pip install --pre --upgrade easyremote

# 一次性身份配置（为签名调用与回执链建立身份）。
# 使用 EasyNet-Cli 运维入口启动 device 或 Hub runtime。
# `node.serve()` 只连接该 operator-managed runtime。
easynet pair
easyremote doctor                            # 可选：逐项体检运行时
```

之后就是上面的 12 行。首次运行若未配对，`node.serve()` 不会伪造身份；它会清楚
打印唯一需要的操作 `easynet pair` 后退出。配对完成后，EasyNet operator 管理的
runtime 必须已经运行。同一脚本会连接 runtime、启动 Python warm host，并发布
全部已注册函数。配对提供 caller identity 与签名；选择 device 只决定函数在哪里
执行，不会向调用者开放整台机器。

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

二进制 frame 不经过 JSON 或 base64 转换，原始 bytes 与 media type 会被完整
保留；调用仍然具有与普通函数结果一致的签名与 receipt-backed 完成语义。
JSON generator 也使用同一个 `.stream(...)` 接口。

---

## 项目状态

EasyRemote v2 当前处于 alpha 阶段，不兼容 v1。当前已经支持类型化同步与异步
函数、有限 server stream、原始 binary/media frame、device targeting、warm
provider、caller context 和签名 invocation receipt。

使用 EasyRemote 需要已配对且正在运行的 EasyNet runtime。跨设备延迟和带宽取决于
实际部署，本 alpha 不宣称统一网络 SLO。request-side media streaming、组合式
`ctx.call` receipt chain 和完整 receipt-chain fetch verification 尚未完成。

详细架构说明见 [`v2 design`](docs/design/easyremote-v2-easynet-refactor.md)。

## 归属与引用

EasyRemote 使用 MIT 许可证。EasyNet 运行时依赖是 Apache-2.0 项目，见 [`NOTICE.md`](NOTICE.md)。用于定位设计的系统与研究参考文献集中列在 [`docs/REFERENCES.md`](docs/REFERENCES.md)。

## License

[MIT](LICENSE) © Silan Hu
