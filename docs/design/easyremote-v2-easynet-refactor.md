# EasyRemote v2 迁移规格说明书（SPEC）

> 状态：**SPEC v1.1**（2026-07-18 canonical runtime ownership 修订）
> 作者：Claude 起草，CTO Silan.Hu 逐轮裁定
> 读者：EasyRemote / EasyNet 工程团队
> 性质：normative——实现与本文冲突时，以本文为准或先修订本文
> 配套：EasyNet-Cli 侧 3 个 PR（§9），独立工作流
> 参考：系统论文、协议和第三方归属集中列在 [`../REFERENCES.md`](../REFERENCES.md)

---

## 0. 定位与叙事（normative，约束一切对外文案）

**主框架：分享的最小单位，从"一次部署"塌缩到"一个函数"。**

- 产品一句话（EN）：**EasyRemote turns a local function into a globally
  callable capability.**
- 产品一句话（CN）：把一个本地函数，变成一个全球可调用的 capability。
- 类比谱系（capability publication 这一层的正确参照，不是 torchrun）：
  Git 把分享代码的单位从项目降到 commit；Docker 把部署软件的单位从机器
  降到镜像；**EasyRemote 把共享服务的单位从 deployment 降到 function**。
- capability 的最小语义（**定义，非场景**）：callable + discoverable +
  composable。
- 系统抽象链（论文线主轴，与 AXIOM/RFC-001 本体逐项同构——function 即
  实现资源面，capability 即 Ability，其后即 Invocation 与 Receipt）：

  ```text
  Function → Capability → Invocation → Receipt
  ```

- 研究 claim（论文线）：EasyRemote/EasyNet makes remote execution
  **verifiable**（receipt / authority / provenance / accountability）。
  产品叙事卖抽象（function → capability），论文叙事卖机制（invocation →
  receipt）——同一条抽象链的前半段和后半段，不是两套话术。

**叙事层级**：

| 角度 | 位置 |
|---|---|
| 可组合（capability = callable + discoverable + composable） | 主框架：标题与开篇 |
| 可达性（NAT / 够不着） | 约束段：解释"为什么过去必须部署" |
| 算力 / GPU 池 | 推论与第一落地场景："算力共享是副产品" |
| 可验证执行 | 隐形地基 + agent 章节入场券；moat 与论文 claim |
| AI-Native | 论证而非标签：agent 是新调用者，组合是新运行时 |

**禁用清单**（CTO 明确否决）：marketplace/"算力成为商品"；"去中心化/
Web3" 词汇；"AI时代下"式前缀；"函数获得身份"式表述（身份属于 node/
ability，函数是实现；用户几乎不接触身份层）；**torchrun 类比**（torchrun
解决 process orchestration，本项目解决 capability publication，层不同；
v1 tagline "Torchrun for the World" 自此退役）。

**判别标准**：`Function → Capability → Invocation → Receipt` 是系统抽象
链，能写论文也能做系统；`Function → GPU Pool → Agent → Marketplace` 是
营销故事链，只能写融资材料。叙事一律沿前者展开，场景只作落点举例。

canonical 文案全文见附录 A（README hero / landing page 母版）。

---

## 1. 目标与非目标

### 1.1 目标

1. EasyRemote 重构为 EasyNet 栈之上的**纯 Python facade**（目标 ~2.5k LOC），
   协议、传输、身份、回执全部下沉到底座。
2. 保住当前可验证的产品资产：12 行 hello-world、`Server / ComputeNode /
   Client / @remote` 表面 API、流式调用、pipeline 编排、examples 入口。
3. 兑现 v2 当前主线：EasyNet identity、签名调用语义、host_stream warm
   execution、receipt-ready invocation envelope。MCP 投影与 `Context.call`
   服务端组合不写入本期完成范围。
4. 退役 v1 自有基础设施约 1.5 万行（§7.2）。

### 1.2 非目标

- 不做 marketplace / 计费 / 结算（回执链为其留了根基，但本期不实现）。
- 不在 facade 内实现任何编排运行时（编排编译到 EAL，由 daemon 执行）。
- 不支持 pickle 参数透传（显式破坏性变更，见 §7.1）。
- 不替代 Ray/Modal 的单集群并行计算场景。

### 1.3 不变式（违反即 reject 的设计红线）

1. facade 不私造协议语义——Invocation、URA、receipt、传输与 daemon
   生命周期一律来自 `easynet_sdk`；其内部协议实现不构成 EasyRemote 的
   第二个 SDK 依赖入口。
2. 七元组字段在公开边界**永远可检视**；公开调用必须显式选择
   `InvocationDerivationPolicy` 或提供完整字段。不得静默以 callee、
   descriptor 或空 causal context 补全 tuple。
3. 产品调用只走 daemon.sock 的 `axon.v1.Invocation`；**不碰 JSON control
   帧**（已降级为 boot/status 专用）。
4. URA 一律通过 `easynet_sdk.AddressingClient` 或 SDK 顶层 builder
   生成、投影和校验，禁止手写字符串插值或在 facade 内实现语法。
5. register 产出的 capability 必须三面同源（callable / discoverable /
   composable 来自同一个 ability 注册），任何让三者分叉的设计被拒绝。

---

## 2. 术语与本体绑定

| EasyRemote 词汇 | EasyNet 本体 | 备注 |
|---|---|---|
| function（用户写的函数） | 实现资源面（implementation plane） | 无网络身份 |
| capability（注册产物） | **Ability**（网络可见契约） | URA + schema + 验证边界 |
| ComputeNode | device runtime 的下游 authoring consumer | 身份来自 pairing |
| 一次调用 | **Invocation**（签名七元组） | caller/callee/ability/subject/nonce/causal/args |
| 调用结果 | Receipt 的 payload | result-first，receipt-always-available |
| Pipeline | Mission / EAL 程序 | 每 step 是子 invocation |
| MCP tool | ability descriptor 的投影 | daemon 自动生成，无独立目录 |

---

## 3. 底座依赖面（冻结清单）

facade 只允许依赖以下接口；新增依赖需修订本节。完整盘点见附录 B。

### 3.1 历史快照：libeasynet_cli C ABI v3（当前实现使用 ABI v7）

daemon 生命周期 4（start/stop/status/invocation_endpoint）、客户端会话 3
（init/shutdown/open_client）、一元 1（invocation_invoke）、服务端流 2
（stream_open/stream_cancel）、双向流 4（bidi_open/send/close/cancel）、
工具 3（abi_version/last_error/string_free）。

### 3.2 daemon Invocation 端点

`~/.easynet/daemon.sock` 上的 gRPC `axon.v1.Invocation`。
`DaemonInvocation`（`EasyNet-Cli/src/daemon/invocation.rs:16`）：
`caller_ura, callee_ura, ability, subject_ura, nonce[16],
causal_context, args: bytes, content_type, metadata,
caller_signature?`。

### 3.3 daemon 系统 ability（facade 消费子集）

`discover`、`invoke`、`mission.run/track/cancel`、`federation.join/
advertise_agent/advertise_abilities/heartbeat/revoke/resolve`、`skill.*`、
`consent/permission`。

### 3.4 ability 注册模型（`EasyNet-Cli/src/core/ability_spec.rs:174`）

`AbilityManifest = { schema_version, name, description, timeout_seconds,
input_schema(JSON Schema, 必填), output_schema?, exec(shell|eal), access }`。

### 3.5 EasyNet-Cli Python SDK（`EasyNet-Cli/sdk/python`）

- Runtime Core：完整 Invocation、prepare/sign/submit、unary/stream/bidi
  与 lifecycle handle。
- Addressing：URA 解析与构造、descriptor reference projection。
- Receipt：receipt reference、验证与因果链投影。
- Runtime connection：discovery、handshake、endpoint、连接状态与错误 taxonomy。
- EasyRemote 只依赖这个 SDK；其内部使用的协议实现由 CLI SDK 维护。

### 3.6 拓扑约束

hub 绑 TCP 必须 TLS（Invariant 2，无明文后门）；device 禁绑 TCP、只出不
进（Invariant 1）。这些部署约束、TLS material 与 process lifecycle 全部由
EasyNet-Cli provider 持有；EasyRemote 不创建或写入 daemon 配置。

---

## 4. 架构

```
┌─────────────────────────────────────────────────────────────┐
│  easyremote v2（纯 Python facade，目标 ~2.5k LOC）            │
│                                                              │
│  client.py     Client / AsyncClient / @remote / Stream       │
│  node.py       ComputeNode / RegisteredFunction / AbilityInfo│
│  context.py    Context（服务端组合）                          │
│  runtime_provider.py SDK RuntimeConnection consumer seam      │
│  schema.py     类型注解 → input/output JSON Schema            │
│  pipeline.py   Pipeline / MissionRun → EAL → mission.run      │
│  invocation.py SDK InvocationResult 展示 / 版本化公开边缘适配  │
│  receipts.py   SDK RuntimeReceipt 投影 / 版本化公开边缘适配    │
│  errors.py     8 类异常                                       │
│  config.py     configure() / 发现链 / doctor                  │
│  _sdk_transport/ SDK adapter 与产品错误映射（私有）           │
│  _host/        warm host_stream 宿主（私有）                   │
└──────────────┬─────────────────────────┬─────────────────────┘
               │ Invocation/URA/回执/RuntimeConnection
                         ┌──────▼──────────┐
                         │   easynet_sdk   │
                         └──────┬──────────┘
                                   ~/.easynet/daemon.sock
                              ┌──────────▼──────────┐
                              │   easynet-daemon     │
                              │ device / hub / both  │
                              └─────────────────────┘
```

### 4.1 关键设计决策

**D1 签名策略。** daemon-local unary 快路径（Local-fast admission）默认不带
`caller_signature`；`sign=True` 的 unary 与 C ABI server-stream 均由 SDK 从
本机 key-service 解析调用者绑定的 active managed key（purpose
`user_signing.cli`）后签名。`Client(signer=...)` 只用于锁定预期 key，不能替代
key-service custody；legacy、外部、已轮换或 owner 不匹配的 signer 在提交前拒绝。
当前 SDK 尚无 signed-bidi carrier，因此 `session(..., sign=True)` 明确返回
`signed_bidi_unsupported`，不会静默降级。

**D2 warm 进程（v1 "0ms always-warm" 卖点的存续）。** 当前实现只有一条
执行路径：`ability deploy --node local` 安装 `exec.kind = "host_stream"`
的 SystemAgent-owned ability；Device 仅为执行宿主，能力归属其
`ability-management` SystemAgent。daemon 直接连接 `_host.HostServer` 的 Unix socket，
发送 `{request: {fn, args, caller, call_id}}`，宿主返回 `stream_item` /
`terminal` / `error` 帧。没有 shell 转发器、Python forwarder、C fastpath
三套旁路。

**D3 负载均衡两阶段安家。** facade 不解析 Ability URA：

- Phase 1（本期，零 daemon 改动）：客户端选点——
  `discover` 拿候选 → `pick` 策略只挑一个 canonical `ability_ura`
  → 通过本机 daemon 的 `<self>.invoke {ability_ura, args}` 调用。
  owner/callee/public ability/local registry key 的投影一律由
  EasyNet-Cli `AbilitySelector` / Axon parser 负责。
- Phase 2（Cli PR-2）：hub 侧 `pool.dispatch` 转发 ability——选点决策以
  子 invocation 出现在回执链上。落地后 `pick="hub"` 启用，客户端策略保留。

### 4.2 分发与运行前置（新增规范）

- **当前 EasyRemote wheel 是纯 Python facade，不捆绑 `libeasynet_cli`**。
  加载顺序：显式 `configure(library_path=...)` / `EASYNET_CLI_LIB` →
  平台 wheel 可选内置路径（仅当专门的二进制 wheel 产线实际放入该文件）→
  系统路径。ABI 版本握手：`easynet_abi_version() == 3`，不匹配抛
  `Unavailable(reason="abi_mismatch")`。
- **easynet-daemon 不随 wheel 分发**。client/node 均要求本机有已安装、
  已 pairing 且由 EasyNet-Cli 启动的 daemon。缺失时报错信息直接给出安装与
  `easynet pair` 命令。
- `easyremote doctor`（CLI 入口）：诊断 lib 加载、control.json、daemon
  存活、credentials、ABI/IPC 版本，输出逐项 ✓/✗。
- `easyremote ability install/list/show` 与 `easyremote agent add/list/stop/refresh`
  均为 Python control facade 的薄 CLI 包装；内部走完整 Invocation 调
  daemon system ability，不 shell 到 `easynet` CLI。`ability list --scope realm`
  显式读取 daemon 的 hub-published 网络目录；默认 `local` 只读本 daemon。
- 依赖：仅 `easynet_sdk`；不直接依赖 grpcio/protobuf 或 Axon SDK。

---

## 5. SDK 公开接口规范（normative）

### 5.0 产品原则

0. **register 产出的是 capability，capability 的定义就是接口清单。**
   注册后同一函数同时满足三重最小语义：callable（Client / `@remote`）、
   discoverable（MCP 投影 + `discover`，零额外 API）、composable
   （Pipeline 引用 + `Context.call`）。任何让三者不同源的设计被拒绝。
1. **12 行体验不破坏。** 唯一新增前置是一次性 `easynet pair`。
2. **三层渐进暴露。** L0：`register`/`execute`，零协议词汇；L1：选点、
   流、超时；L2：SDK canonical draft、runtime receipts、causal、签名。
   每层升级只隔一个属性访问。
3. **Result-first，receipt-always-available。**
4. **错误即 taxonomy**，不发明第 8 类运行期错误。
5. **不留 pickle。** 参数默认 JSON；二进制媒体显式 `content_type` + 流。
6. **sync-first + `.aio` 镜像**，不做双 API 分裂。
7. **facade 零协议发明。**

### 5.1 顶层导出

```python
__all__ = [
    # 产品 authoring / invocation
    "ComputeNode", "Client",
    # daemon control facades（普通 Invocation，不拥有 process lifecycle）
    "AbilityControl", "AbilityRecord", "AbilityInstallResult",
    "AgentControl", "AgentRecord", "AgentStartResult", "AgentStopResult",
    # 调用
    "remote", "Invocation", "PreparedInvocation", "InvocationState",
    # 服务端组合
    "Context",
    # 1.0.0 删除的版本化公开边缘适配
    "InvocationTuple", "Receipt", "ReceiptChain",
    # 流
    "Stream", "BidiSession",
    # 编排
    "Pipeline", "MissionControl", "MissionRun",
    # 错误
    "RemoteError", "Cancelled", "DeadlineExceeded", "Unavailable",
    "InvalidArgument", "ResourceExhausted", "PermissionDenied",
    "InternalError", "SchemaError",
    # 配置
    "configure",
]
```

### 5.2 authoring hello-world（验收基准）

```python
# EasyNet-Cli 已完成 pairing、runtime 配置与进程启动。
from easyremote import ComputeNode
node = ComputeNode()

@node.register
def ai_inference(prompt: str) -> str:
    return model.generate(prompt)

node.serve()

# 调用方（任何地方）
from easyremote import Client, FreshRoot, ResolvedTargetSubject
client = Client(invocation_policy=FreshRoot(ResolvedTargetSubject()))
print(client.execute("ai_inference", "Hello EasyNet"))
```

### 5.3 Runtime ownership

EasyRemote 不公开 daemon/Hub lifecycle API，不生成 TLS material，不写
`daemon-config.toml`，也不启动、停止或 adopt daemon process。
`LocalRuntimeProvider.connect()` 直接返回 SDK `RuntimeConnection`；
`ComputeNode.stop()` 只关闭该连接与本地 warm host。Hub/device 部署策略、
配置和 process lifecycle 统一由 EasyNet-Cli provider 管理。

### 5.4 `ComputeNode`

```python
class ComputeNode:
    def __init__(
        self,
        gateway: str | None = None,        # v1 兼容位置参数；None → credentials.json
        *,
        namespace: str = "er",             # ability URA 命名空间（§6 待拍板）
        daemon: str | Path | None = None,  # 显式 control.json/endpoint；None → 自动发现
        warm: bool = True,                 # warm host；False = 每调用冷启动
    ): ...

    def register(
        self,
        fn=None,
        *,
        name: str | None = None,           # 默认函数名
        description: str | None = None,    # 默认 docstring 首行
        timeout: float | None = None,
        stream: bool | None = None,        # None → generator 自动判定
        schema: dict | None = None,        # 显式覆盖推导 input_schema
        access: Literal["private", "realm", "public"] = "realm",
    ) -> RegisteredFunction: ...

    def serve(self) -> None                # 阻塞（v1 兼容）；SIGINT 优雅退出
    def start(self) -> None                # 非阻塞
    def stop(self) -> None
    def __enter__/__exit__                 # with 语法 = start/stop

    @property
    def abilities(self) -> list[AbilityInfo]   # 含完整 URA 与 mcp_tool 投影名
    @property
    def device_ura(self) -> str                # 来自 pairing，只读
```

**schema 推导规则（`schema.py`，table-driven 单测覆盖）：**

| Python 形态 | input_schema |
|---|---|
| 基本类型注解（str/int/float/bool/list/dict、Optional、Literal） | 对应 JSON Schema；required 按默认值推导 |
| `pydantic.BaseModel` 参数 | `model_json_schema()` 内联 |
| `dataclass` 参数 | 字段展开为 object schema |
| 无注解参数 | 宽松 `{}` + 注册时 `UserWarning` |
| 不可 JSON 化注解 | 注册时抛 `SchemaError`，给三条出路（补注解 / pydantic 化 / 二进制流） |
| generator 函数 | 注册为流 ability；yield 类型 → chunk schema |
| 返回注解 | `output_schema` |
| 首参注解为 `Context` | 注入，schema 推导跳过 |

注册产物：`AbilityManifest` 写盘 → ability deploy → URA 由
`easynet_sdk.device_ability_ura(...)` 生成并经 SDK Addressing provider
往返校验。
调用期参数校验在 daemon 侧由 input_schema 执行；facade 客户端做同 schema
的 fail-fast 预检。

**MCP 投影（discoverable，零节点侧 API）：** 注册即投影。daemon 把
ability descriptor 自动投影为 MCP tool spec（`easynet mcp_server` /
`easynet start --mcp`）。facade 不复刻目录；`AbilityInfo.mcp_tool` 仅供
检视。

### 5.5 `Context`（当前只读身份注入；组合面待 receipt URA）

当前 v2.0.0a0 已落地的是 `host_stream` envelope 注入的只读上下文：
`ctx.invocation_id` 与 `ctx.caller`。服务端子调用、progress、inbox/cancel
等组合方法在 facade 中保留为显式 API stub，但会抛
`Unavailable(reason="context_dispatch_not_wired")`。原因是 child invocation
必须携带可验证的 parent receipt URA；在 RFC-007/008 的 receipt body URA /
full-receipt fetch 路径落地前，facade 不会伪造 causal reference。

**当前可用：**

```python
from easyremote import Context

@node.register
def quarterly_report(ctx: Context, quarter: str) -> str:
    return f"{quarter} requested by {ctx.caller} in {ctx.invocation_id}"
```

**显式组合面：**

```python
class Context:
    invocation_id: str
    caller: str                        # 调用方 URA（问责语义：谁在叫我）

    @staticmethod
    def target(
        function: str,
        /,
        *,
        invocation_policy: FreshContextChild,
    ) -> ContextTarget

    def call(self, target: ContextTarget, /, *args, **kw) -> Any
    def invoke(self, target: ContextTarget, /, *args, **kw) -> Invocation
    def stream(self, target: ContextTarget, /, *args, **kw) -> Stream

    def progress(self, payload: dict | bytes) -> None
    def recv(self, timeout: float | None = None) -> InboundMessage | None
    @property
    def cancelled(self) -> bool
```

目标底层映射：Axon `AbilityContext`（invocation_id / emit_progress / inbox /
supervisor）+ daemon `invoke` 系统 ability。`ctx.call` 是 composable 的
服务端兑现目标：能力像库一样互相调用，每一跳都在回执链上。调用方必须通过
`Context.target(..., invocation_policy=FreshContextChild(...))` 显式选择
subject policy；host 只把 daemon 提供的 parent receipt anchor 绑定进该 policy，
不会替调用方默认 subject、nonce 或空 causal context。

### 5.6 `Client` 与 `@remote`

```python
class Client:
    def __init__(
        self,
        gateway: str | None = None,        # None → credentials.json
        *,
        timeout: float = 30.0,
        invocation_policy: InvocationDerivationPolicy | None = None,
        retry: RetryPolicy | None = None,  # 默认仅对带 retry_after 的
                                           # UNAVAILABLE/RESOURCE_EXHAUSTED 退避重试
    ): ...

    @property
    def invocation_policy(self) -> InvocationDerivationPolicy | None: ...

    # L0：v1 兼容
    def execute(self, target: str | CallTarget, /, *args, **kwargs) -> Any

    # L1：选点 / 流 / 超时
    def call(self, target: str | CallTarget, /, *args, **kwargs) -> Any
    def stream(self, target: str | CallTarget, /, *args, **kw) -> Stream
    def session(self, target: str | CallTarget, /, **kw) -> BidiSession

    @staticmethod
    def target(function: str, /, *, node: str | None = None,
               pick: Literal["round_robin", "random"] | None = None,
               timeout: float | None = None,
               metadata: dict[str, str] | None = None,
               invocation_policy: InvocationDerivationPolicy | None = None
               ) -> CallTarget

    # L2：完整调用对象
    def invoke(self, target: str | CallTarget, /, *args, **kwargs) -> Invocation
    def prepare(self, target: str | CallTarget, /, *args, **kw) -> PreparedInvocation

    # 发现（discoverable 的程序化面）
    def functions(self) -> list[FunctionInfo]   # discover 投影
    def nodes(self) -> list[NodeInfo]           # federation.resolve 投影

    @property
    def aio(self) -> AsyncClient                # 同形 async 镜像（方法名不变）
```

```python
policy = FreshRoot(ResolvedTargetSubject())

@remote(invocation_policy=policy)
def ai_inference(prompt: str) -> str: ...      # typed stub，函数体永不本地执行

ai_inference("hi")                    # L0 透明调用
ai_inference.stream("hi")             # L1 流
await ai_inference.aio("hi")          # async 镜像
client = Client(invocation_policy=policy)
client.call(Client.target("ai_inference", node="gpu-1"), prompt="hi")

prepared = client.prepare("ai_inference", prompt="hi")  # L2：draft 检视
prepared.tuple.subject_ura
# PreparedInvocation.send()/Client.invoke() 保留给 daemon unary/system ability；
# EasyRemote-hosted ability 统一由 call()/stream() 消费 host_stream carrier。
```

**参数编码**：默认 `application/json`；`bytes` 参数 + 显式
`content_type=` 走二进制（媒体帧场景）；其余一律 JSON Schema 校验。
**无 pickle 通道。**

### 5.7 `Invocation` / `PreparedInvocation` / 回执

```python
class PreparedInvocation:
    draft: easynet_sdk.InvocationDraft
    tuple: easynet_sdk.InvocationDraft | InvocationTuple
    def with_subject(self, ura: str) -> "PreparedInvocation"
    def with_causal(self, causal: LegacyCausal) -> "PreparedInvocation"
    def send(self) -> Invocation

class Invocation:
    id: str
    state: easynet_sdk.InvocationLifecycleState
    tuple: easynet_sdk.InvocationDraft
    sdk_result: easynet_sdk.InvocationResult

    def result(self) -> Any

    @property
    def receipt(self) -> easynet_sdk.RuntimeReceipt | None
    def receipts(self) -> tuple[easynet_sdk.RuntimeReceipt, ...]
```

EasyRemote 不定义 canonical bytes、receipt chain continuity、签名或
admission 规则。已发布的 `InvocationTuple`、`Receipt`、`ReceiptChain` 与
`PreparedInvocation.with_causal` 仅作为 policy 枚举的产品边缘形状保留；
构造后立即委托 SDK 生成或解析 canonical 对象，内部生产路径不得调用这些
适配器。机器策略 `easyremote/edge-adapter-policy.v1.json` 记录当前包版本
`2.0.0a0`、删除版本 `1.0.0`、精确公开字段及零新增内部调用者约束。
`ReceiptChain.verify_continuity()` 不在 runtime summary 上重写 chain 规则；
完整回执链验证使用 `easynet_sdk.ReceiptClient.verify_chain`。

### 5.8 错误层级

```python
class RemoteError(Exception):
    kind: str                     # 7 类 taxonomy 之一
    reason: str                   # 稳定机器标识
    invocation_id: str | None
    retry_after: float | None
    @property
    def retriable(self) -> bool

class Cancelled(RemoteError): ...            # CANCELLED
class DeadlineExceeded(RemoteError): ...     # DEADLINE_EXCEEDED
class Unavailable(RemoteError): ...          # UNAVAILABLE
class InvalidArgument(RemoteError): ...      # INVALID_ARGUMENT（含 schema 校验失败）
class ResourceExhausted(RemoteError): ...    # RESOURCE_EXHAUSTED
class PermissionDenied(RemoteError): ...     # PERMISSION_DENIED（含 consent 拒绝）
class InternalError(RemoteError): ...        # INTERNAL
class SchemaError(ValueError): ...           # 注册期：注解无法成 schema
```

C ABI 错误码、gRPC code、daemon 拒绝原因全部收敛到这 8 类；
`easynet_last_error()` 消息进 `str(exc)`。

### 5.9 `Pipeline`（客户端编排 → EAL——composable 的第二半）

step 可引用三种来源，组合不限于自己的函数：

```python
pipe = Pipeline("nightly-report")

fetch = pipe.step("teamA.fetch_sales", quarter="Q2")   # ① 别人的能力：按名字引用
summary = pipe.step("er.summarize", rows=fetch.output) # ② 上游输出作为 dataflow
pipe.step(publish_report, body=summary.output)         # ③ RegisteredFunction 引用

run: MissionRun = pipe.run(label="nightly")
run.status                       # mission.track 投影
run.cancel()
print(pipe.to_eal())             # 可检视 EAL 源，含强制 provenance 头
                                 # （created_by = 当前用户 URA）
```

语义：编译为 EAL → `mission.run`（args `{source, label}`，返回
`{ok, run_id, run_dir, outputs, meta}`）；每 step 是子 invocation，回执链
完整。**facade 不自建编排运行时**。

产品归属：Mission plan/step/output、status/child-fact conformance、run
projection、event tailer 和 execution adapter 都由 EasyRemote 持有；它们只
通过通用 `Client.invoke` 调用 daemon。easynet-sdk 不提供 Mission 产品
facade、system-ability enum 或 profile bridge。

已有 EAL 源直接运行，不需要构造 `Pipeline`：

```python
client = Client()
client.missions.run_eal(source, label="nightly")
client.missions.run_file("nightly.eal")
client.missions.track("run-1")
client.missions.cancel("run-1")
```

### 5.10 配置与发现

```python
easyremote.configure(
    credentials: Path | None = None,   # 默认 ~/.easynet/credentials.json
    control: Path | None = None,       # 默认 ~/.easynet/control.json
    library_path: Path | None = None,  # libeasynet_cli 显式路径
)
# 等价环境变量：EASYNET_CREDENTIALS / EASYNET_CONTROL_JSON / EASYNET_CLI_LIB
```

传输连接链路：`Client()` → control.json → daemon.sock；身份 →
credentials.json。公开 dispatch 仍必须显式选择 invocation policy。缺失运行时
配置时报错给出 `easynet pair` / `easynet start` 命令。
CLI 入口：`easyremote doctor` / `easyremote ability ...` /
`easyremote agent ...`（§4.2）。

### 5.11 async 镜像

`client.aio` 返回 `AsyncClient`：方法名与签名同 `Client`，全部
coroutine；`Stream` 同时实现 `__iter__` 与 `__aiter__`；
`RemoteFunction.aio(...)` 为 coroutine。无独立 async 包。

---

## 6. URA 与数据模型映射（按 ura-discipline：缺口举旗不发明）

| 实体 | canonical 形状（一律 builder 生成） |
|---|---|
| 注册函数 → ability | `easynet_sdk.device_ability_ura(...)` |
| caller | SDK runtime identity projection 的 device URA |
| subject | 显式 `InvocationSubjectPolicy` 选择的 SDK-validated URA |

**调用侧 URA 纪律**：当用户传入 canonical Ability URA（通常来自
`FunctionInfo.ability_ura`）时，facade 只做产品 target selection；owner
投影、descriptor binding 和完整 Invocation draft 构建分别委托给 SDK
`AddressingClient` 与 `AbilityInvocationClient`。`pick` 也只选择候选项，
不在 EasyRemote 内解析或重建 URA。

**待拍板 / spec 缺口：**

1. **namespace `er`**：需 CTO 拍板并记入 RFC-001 §URA 实践注记
   （备选：`fn` / 用户自定义）。
2. **daemon 运行时注册 ability（免重启）**：已 P0 实测，见 §6.2-④。
3. **receipt body URA**：RFC-007/008 在途；facade 只把 receipt 当对象
   暴露，不构造 receipt URA。
4. **节点负载指标**：resource-aware 选点数据源，Cli PR-3（§9）。

### 6.2 历史 P0 实测结论（2026-06-11，daemon v0.64.8 / ABI v3）

全链路活体验证**通过**：identity（credentials→device URA）→ 七元组
编码 → C ABI → daemon.sock gRPC → dispatch → 响应解码，`demo.discover`
真调 COMPLETED；集成套件 4/4 绿。逐项钉子：

| # | 结论 | facade 影响 |
|---|---|---|
| ① | 磁盘上的 release dylib 曾是 v1/v2 旧产物（只导出已弃用的 `easynet_ability_invoke` 面）；重建后 17 符号与头文件逐一对齐 | 绑定层已加固：先握手后声明全集，旧库报 `abi_mismatch`/`abi_symbol_missing` + 重建指引 |
| ② | 历史 daemon 曾在 unary 路径返回空 receipt | 不保留兼容 fallback；当前 live contract 要求 SDK `RuntimeReceipt`，缺失即集成失败 |
| ③ | Ability URA 形状由 SDK Addressing provider 验证 | `FunctionInfo.ability_ura` 为内部 canonical 字段，`qualified_name` 保留产品读取兼容 |
| ④ | **本体修正：User、SystemAgent、Device 三者分离**。User 是问责 caller，SystemAgent 是行为 owner/callee，Device 只是 execution host。正确通路是 User 调用目标 Device 的 `ability-management` SystemAgent 执行 `ability.deploy`，部署后的 URA = `easynet:///r/<realm>/ability/system-agent.<node-id>.ability-management.<ns>.<fn>` | `ComputeNode` 只打包由 `ability-management` SystemAgent 拥有、在 Device 上执行的 ability，不再写 agents.json/TOML，不再调用 agent refresh |
| ⑤ | **闭环执行模型唯一化**：register → ability.json → Python ResourceRef → daemon `ability.deploy` Invocation → daemon `host_stream` executor → warm host → stream frames/terminal | `Client.call()` drains host_stream for result-first use；`Client.stream()` exposes live frames；`Client.invoke()`/`PreparedInvocation.send()` 保留给 daemon unary/system ability |
| ⑥ | **无 forwarder 旁路**：warm host 路径不维护 shell forwarder / Python shim / C fast forwarder 三套实现 | latency 与正确性只看 daemon `host_stream` executor 直接连 Unix socket 的正式路径 |
| ⑦ | gRPC / C ABI 错误折叠仍可能把 daemon 细节压进 `last_error` | facade 只做 taxonomy 映射，不发明路由语义 |

---

## 7. v1 → v2 兼容与退役

### 7.1 兼容矩阵

| v1 写法 | v2 行为 |
|---|---|
| `Server(port).start()` / `easyremote hub` | **破坏性删除**；Hub 配置与 process lifecycle 归 EasyNet-Cli operator/provider |
| `easyremote ability install/list/show` | 可用；CLI 走 `AbilityControl`，支持 local/realm catalogue scope |
| `easyremote agent add/list/stop/refresh` | 可用；CLI 走 `AgentControl` |
| `easyremote mission run/track/cancel` | 可用；CLI 走 `MissionControl`，运行已有 EAL 源 |
| `node.register` / `node.serve()` | 不变 |
| `Client.execute("fn", args)` | 不变（JSON 可表达参数） |
| pickle 参数（自定义对象） | **破坏性变更**：`InvalidArgument`，报错给出 pydantic/二进制流出路 |
| `@remote(node_id=…)` | 破坏性删除；v2 只接受 `node=` |
| `@remote(load_balancing={…})` | 破坏性删除；客户端显式使用 `Client.target(..., pick=...)` |
| `MCPGateway` / `A2AGateway` | 移除；文档指向 `easynet mcp_server` 与原生 invocation |
| `RemotePipeline` 本地 DAG | `Pipeline` → EAL；API 形似、执行体换底 |
| `Serializer` / `NodeHealthMonitor` 直接引用 | 移除，无替身（底座职责） |

### 7.2 退役清单（v1 代码删除项，约 1.5 万行）

| 模块 | 处置 |
|---|---|
| `easyremote/core/protos/`（service.proto + 生成码） | 删除——协议由 axon.v1 取代 |
| `easyremote/core/data/serialize.py`（pickle/压缩） | 删除——JSON + content_type 取代 |
| `easyremote/core/balancing/`（策略框架 + health_monitor） | 删除——策略移植为 `pick` 纯函数；健康归 federation.heartbeat |
| `easyremote/core/nodes/{server,compute_node,client}.py` | 删除——facade 重写 |
| `easyremote/protocols/`、`easyremote/mcp/`、`easyremote/a2a/` | 删除——daemon MCP 投影 / 原生 invocation 取代 |
| `easyremote/agent_service.py`、`easyremote/device_host.py` | 退役——功能由 daemon `skill.*` + ability deploy 承接；如需保留产品形态另立 RFC |
| `easyremote/decorators.py`、`easyremote/skills.py` | 重写进 `client.py` / `pipeline.py` |
| 依赖 | 移除 grpcio/protobuf 与直接 Axon SDK 依赖；仅依赖 `easynet_sdk`，其 native runtime 由 EasyNet CLI 安装或显式路径提供 |

---

## 8. 实施计划（P0–P5）

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **P0 链路验证**（1–2 天） | device daemon + SDK Invocation provider + runtime adapter；核实运行时注册路径 | canonical draft、终态和 receipt 均由 SDK 投影；结论写入本文 §6.2 |
| **P1 `_sdk_transport`**（~3 天） | 组合 SDK adapter、error taxonomy、stream 与 bidi facade | EasyRemote 不加载 C ABI，不复制 stream/unary state machine |
| **P2 节点侧**（~1 周） | `schema.py` 推导；`register` → ability package → deploy；`_host` host_stream socket | 注册函数可被 daemon `host_stream` executor 调用；无 forwarder 文件 |
| **P3 客户端侧**（~1 周） | `execute/call/invoke/prepare/stream/session` + `@remote` + `.aio` + read-only `Context` | §5.2 authoring demo 原样跑通；stream terminal/error 语义有单测 |
| **P4 runtime boundary + 选点**（~1–2 周） | `RuntimeConnection` consumer provider + ownership gate；客户端 `pick` 策略 | 无 daemon/Hub lifecycle authority；双节点同名函数按策略分流 |
| **P5 pipeline + 退役**（~1 周） | `Pipeline`→EAL→`mission.run`；执行 §7.2 删除清单 | examples smoke tests 全绿；wheel 不含 grpcio；v1 删除矩阵逐项测试 |

阶段间依赖：P1←P0；P2/P3←P1（可并行）；P4←P3；P5←P2+P3。
风险集中在 P0/P2（warm host、运行时注册），故 P0 先行。

---

## 9. EasyNet-Cli 侧配套项（独立工作流，不阻塞 P0–P3）

| PR | 内容 | facade 受益点 |
|---|---|---|
| PR-2 | hub `pool.dispatch` 系统 ability | `Client.target(..., pick="hub")`，选点上回执链 |
| PR-3 | 节点负载指标进 heartbeat / ability summary | `Client.target(..., pick="resource_aware")` 数据源 |

---

## 10. 测试策略

1. **单测**：schema 推导 table-driven；错误映射全枚举；URA 经
   `parse_ura` round-trip（不变式 4）。
2. **host contract**：用 fake transport / fake host_stream frame 覆盖
   unary、stream、terminal、error、超时、schema 选择。
3. **examples smoke**：`examples/01_hello_node.py` /
   `examples/02_hello_client.py`、`examples/04_streaming_*`、
   `examples/remote_demo_*` 是本期可见入口。
4. **兼容**：§7.1 矩阵逐行用例；删除项不保留 alias 或 shim。
5. **daemon fixture**：真实 easynet-daemon 集成、receipt chain 端到端验证、
   性能基线统一作为后续 release gate，不在本分支 overclaim。

---

## 11. 风险

| 风险 | 缓解 |
|---|---|
| daemon 无免重启注册路径 | P0 探明；缺失则 fail closed 并进入 EasyNet-Cli contract，不在 facade 增加重启逻辑 |
| axon Python SDK stream 包装未定稿 | 流式一律走 C ABI（§3.5），不依赖 SDK 进度 |
| Hub TLS 提高上手门槛 | EasyNet-Cli provider 统一 provisioning 与诊断；EasyRemote 不读取或生成 TLS material |
| 平台 wheel 构建矩阵成本 | 复用 EasyNet-Cli 现有交叉编译产物；首版可只发 mac/linux |

---

## 12. 开放问题（待 CTO 拍板）

1. namespace `er`（§6.1）。
2. PyPI 沿用 `easyremote`（major bump 2.0）还是新包名。

---

## 附录 A：canonical 文案（README hero / landing page 母版）

> # 你写的是一个函数，世界向你要的却是一个服务
>
> 你本地有个能力——一个模型、一段 pipeline、一个查库函数。同事想用，
> agent 想调，别的项目想接。今天的答案是同一套仪式：打包、容器、部署、
> 鉴权、维护。**分享的最小单位是"一次部署"——所以绝大多数能力，从来
> 没被分享过。**
>
> 为什么非部署不可？因为你的机器藏在 NAT 后面，世界够不着它。一块 4090
> 在你桌底吃灰，不是它不够强——放在十年前它是超算——是它没有任何安全
> 地被调用的方式。上传，是过去唯一的出路。
>
> EasyRemote 把分享的最小单位降到一个函数：
>
> ```python
> from easyremote import ComputeNode
> node = ComputeNode()
>
> @node.register
> def ai_inference(prompt: str) -> str:
>     return model.generate(prompt)
>
> node.serve()
> ```
>
> 注册之后，这个函数成为一个 **capability**。capability 不是修辞，它有
> 最小定义——**可调用、可发现、可组合**，三者同时成立：
>
> ```python
> # 同事：像调本地函数
> policy = FreshRoot(ResolvedTargetSubject())
> Client(invocation_policy=policy).execute("ai_inference", "hello")
>
> # Agent：自动投影为 MCP tool，Claude 直接发现、直接调用
> #   claude mcp add easynet -- easynet mcp_server
>
> # 系统：作为 Pipeline 的一步，和别人的函数编排成任务链
> pipe.step("ai_inference", after=[fetch])
> ```
>
> 这不是三个使用场景——**这是 capability 这个抽象的全部语义**。代码和
> 模型留在你的机器上，世界拿到的是调用权，不是副本。
>
> Git 把分享代码的单位从项目降到一次 commit。Docker 把部署软件的单位从
> 一台机器降到一个镜像。**EasyRemote 把共享服务的单位，从一次 deployment
> 降到一个函数。**
>
> **第一个直接的推论：团队 GPU 池。** 当函数留在设备上执行，算力共享是
> 副产品：办公室、家里、宿舍的显卡组成一个推理集群——节点只向外拨号，
> NAT 不是障碍；模型常驻显存，没有冷启动；网关是一台 $5 的 VPS。
>
> **你大概会问：把自己的机器开放出去，不危险吗？** 这正是过去没人敢做
> 这件事的原因。EasyRemote 把每次调用做成签名的调用对象——谁调的、调谁、
> 动什么对象、跟在哪条因果链后——每次执行留下可离线验证的回执。**这一层
> 没有开关、没有配置，你几乎不会意识到它存在**，但它是你敢把机器开放给
> 团队的全部原因。
>
> **而它真正不可替代的时刻，是 agent 要操作真实世界资源的那天。** agent
> 的能力每三个月上一个台阶，问责方式却从未变过：一次 tool call 发出去，
> 剩下全凭它自己汇报。让它查天气无所谓；让它动数据库、下采购单、操作
> 设备——"它做了什么"不能再是自述。签名调用 + 回执链给出的授权语义是：
> **这个 agent、以我的授权、在这条任务链里、可以调这个能力、动这个对象**
> ——细到单次调用，事后逐环可验。我们的演示里，Claude 从一台笔记本指挥
> 另一座城市沙箱中的机器人：演示的不是"能控制"，是每个动作都有签名的
> 命令和可验证的回执。
>
> Ray、Modal、RunPod 把远程执行做**易**，MCP 把工具做**通**；没有人把
> 本地能力做成**可组合、可问责**的服务单元。我们做的是它们之间缺的那
> 一层。
>
> ```
> pip install easyremote
> ```
>
> **云计算让代码迁移到计算资源。EasyRemote 让计算资源留在原地，同时获得
> 全球可调用性。**

---

## 附录 B：底座接口完整清单（reference，2026-06-11 自磁盘盘点）

### B.1 历史接口清单：libeasynet_cli C ABI v3（当前实现使用 ABI v7）

| 函数 | 作用 |
|---|---|
| `easynet_daemon_start(config_json, &handle)` | 按 JSON 配置启动 daemon |
| `easynet_daemon_stop(handle)` | 停止 |
| `easynet_daemon_status(handle, &status_json)` | 存活/状态 |
| `easynet_daemon_invocation_endpoint(handle, &endpoint)` | 取 daemon.sock 路径 |
| `easynet_init(control_json_path, &handle)` | 经 control.json 连接 daemon |
| `easynet_shutdown(handle)` | 断开 |
| `easynet_daemon_open_client(daemon_handle, &handle)` | 从生命周期句柄取 IPC 客户端 |
| `easynet_invocation_invoke(h, invocation_json, &receipt_json)` | 一元调用 |
| `easynet_invocation_stream_open(h, inv_json, on_chunk, ud, &sid)` | 服务端流 |
| `easynet_invocation_stream_cancel(h, sid)` | 取消流 |
| `easynet_invocation_bidi_open(h, inv_json, on_frame, ud, &bid)` | 双向流开 |
| `easynet_invocation_bidi_send(h, bid, frame_json)` | 上行帧 |
| `easynet_invocation_bidi_close(h, bid)` | 优雅关（EOF） |
| `easynet_invocation_bidi_cancel(h, bid)` | 中止 |
| `easynet_abi_version()` / `easynet_last_error()` / `easynet_string_free(s)` | 工具 |

### B.2 daemon 面

- Invocation 端点：`axon.v1.Invocation`（Invoke / InvokeStream /
  InvokeBidi）@ `~/.easynet/daemon.sock`；发现经 `~/.easynet/control.json`
  （socket_path / invocation_endpoint / daemon_identity / IPC 版本协商）。
- 系统 ability（~60，facade 消费子集见 §3.3）；ability manifest 见 §3.4。
- runtime host start/configuration API 属于 EasyNet-Cli provider；
  EasyRemote 不导入或投影这些类型。
- 约束：hub TCP 必须 TLS；device 禁绑 TCP；SIGHUP 仅热载 federated_peers
  与 quota。

### B.3 EasyNet-Cli Python SDK

- `RuntimeClient`：完整 Invocation、prepare/sign/submit、unary/stream/bidi
  与 handle lifecycle。
- `AddressingClient`：URA、ability descriptor reference 与 owner projection。
- `ReceiptClient`：verification、causal receipt reference 与 terminal receipt
  projection。
- `RuntimeConnection`：discovery、handshake、连接状态与关闭；私钥仍由 daemon
  key-service 托管，EasyRemote 不接触密钥材料或 daemon lifecycle。
- EasyRemote 不直接依赖或实例化底层协议 SDK/runtime。
