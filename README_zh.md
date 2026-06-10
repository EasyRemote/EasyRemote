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
from easyremote import Client
Client().execute("ai_inference", prompt="hello")

# Agent：自动投影为 MCP tool，Claude 直接发现、直接调用
#   claude mcp add easynet -- easynet mcp_server

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

Ray、Modal、RunPod 把远程执行做**易**，MCP 把工具做**通**；没有人把本地能力做成**可组合、可问责**的服务单元。我们做的是它们之间缺的那一层。

**云计算让代码迁移到计算资源。EasyRemote 让计算资源留在原地，同时获得全球可调用性。**

---

## 上手

```bash
pip install easyremote

# 一次性前置（类比 ssh-keygen 的一次性成本，换来签名调用与回执链）
easynet pair                                  # 设备配对，签发身份
easynet agent add --type claude-code er      # 注册能力的归属 agent
easyremote doctor                            # 逐项体检：库 / daemon / 身份 / 注册
```

之后就是上面的 12 行。`examples/` 有可直接运行的节点、客户端、编排三个示例。

### 三层调用面（渐进暴露）

```python
client = Client()

# L0 —— 结果优先
client.execute("ai_inference", prompt="hi")

# L1 —— 选点 / 流 / 超时
client.call("ai_inference", prompt="hi", node="gpu-1", timeout=10)

# L2 —— 完整调用对象：七元组进，回执出
inv = client.invoke("ai_inference", prompt="inspect me")
inv.tuple.subject     # 七元组永远可检视
inv.receipts()        # 回执链
```

---

## 适用场景

| # | 场景 | 适用对象 | 解决什么 |
|---|----------|-------------|----------------|
| K1 | **私有 AI 推理池**（团队 GPU 池） | AI 团队 / 研发组 | 团队 GPU 共享推理与负载分摊，消除重复云开销 |
| K2 | **Agent 工具网关**（企业工具网格） | Agent 平台团队 | 统一能力目录，Claude/GPT/自研 agent 直接发现并调用企业函数 |
| K6 | **数据不出域 AI** | 医疗 / 金融 / 政务 | 推理跑在数据所在设备，合规且可问责 |
| K9 | **运行时设备能力注入** | ToC Agent 应用 / 边缘平台 | 不重启即热注册新能力（`easynet agent refresh` 路径已实测） |
| K10 | **Claude Code 机器人指挥**（Commander Skill + MCP） | Agent 产品团队 / 机器人平台 | 在 Claude Code 安装 commander skill 后，通过 MCP 远程部署并操作 client-sandbox 机器人 |

---

## 状态（v2.0.0a0）

v2 是基于 EasyNet 栈（[EasyNet-Axon](https://github.com/EasyRemote/EasyNet-Axon) 协议层 + easynet-daemon）的全新实现，**不兼容 v1**。规格与逐项实测记录见 [`docs/design/easyremote-v2-easynet-refactor.md`](docs/design/easyremote-v2-easynet-refactor.md)。

| 能力 | 状态 |
|---|---|
| 注册 → 热加载 → 调用闭环（warm 宿主） | ✅ 真 daemon 实测全通 |
| 三层客户端 / `@remote` stub / async 镜像 | ✅ |
| Pipeline → EAL → mission.run | ✅ |
| Gateway（hub + 自签 TLS 引导） | ✅ |
| `easyremote doctor` | ✅ |
| 流式 / 服务端 Context 组合 / <50ms warm 延迟 | ⏳ 待 daemon host-attach 协议（EasyNet-Cli 侧） |
| 回执链密码学验证 | ⏳ 待完整回执获取路径（RFC-007/008） |

## License

[MIT](LICENSE) © Silan Hu
