# EasyRemote v2 迁移规格说明书（SPEC）

> 状态：**SPEC v1.0**（2026-06-11 定稿；含同日七轮叙事裁定）
> 作者：Claude 起草，CTO Silan.Hu 逐轮裁定
> 读者：EasyRemote / EasyNet 工程团队
> 性质：normative——实现与本文冲突时，以本文为准或先修订本文
> 配套：EasyNet-Cli 侧 3 个 PR（§9），独立工作流

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
2. 保住 v1 的产品资产：12 行 hello-world、`Server / ComputeNode / Client /
   @remote` 表面 API、流式调用、pipeline 编排、gallery 场景。
3. 兑现 v2 新增价值：签名调用、回执链验证、TLS 强制、MCP 零成本投影、
   服务端组合（`Context.call`）。
4. 退役 v1 自有基础设施约 1.5 万行（§7.2）。

### 1.2 非目标

- 不做 marketplace / 计费 / 结算（回执链为其留了根基，但本期不实现）。
- 不在 facade 内实现任何编排运行时（编排编译到 EAL，由 daemon 执行）。
- 不支持 pickle 参数透传（显式破坏性变更，见 §7.1）。
- 不替代 Ray/Modal 的单集群并行计算场景。

### 1.3 不变式（违反即 reject 的设计红线）

1. facade 不私造协议语义——协议对象一律来自 `easynet_axon`，传输与
   daemon 生命周期一律来自 `libeasynet_cli`。
2. 七元组字段在公开边界**永远可检视**；便捷默认值（`subject=callee`、
   `causal=none`）必须暴露在对象属性上，不得埋进字符串。
3. 产品调用只走 daemon.sock 的 `axon.v1.Invocation`；**不碰 JSON control
   帧**（已降级为 boot/status 专用）。
4. URA 一律 builder 生成（`build_device_ability_ura` / `parse_ura`），
   禁止手写字符串插值。
5. register 产出的 capability 必须三面同源（callable / discoverable /
   composable 来自同一个 ability 注册），任何让三者分叉的设计被拒绝。

---

## 2. 术语与本体绑定

| EasyRemote 词汇 | EasyNet 本体 | 备注 |
|---|---|---|
| function（用户写的函数） | 实现资源面（implementation plane） | 无网络身份 |
| capability（注册产物） | **Ability**（网络可见契约） | URA + schema + 验证边界 |
| ComputeNode | device + 其上的 daemon（device 模式） | 身份来自 pairing |
| Gateway / Server | hub（daemon hub/both 模式） | TLS 强制 |
| 一次调用 | **Invocation**（签名七元组） | caller/callee/ability/subject/nonce/causal/args |
| 调用结果 | Receipt 的 payload | result-first，receipt-always-available |
| Pipeline | Mission / EAL 程序 | 每 step 是子 invocation |
| MCP tool | ability descriptor 的投影 | daemon 自动生成，无独立目录 |

---

## 3. 底座依赖面（冻结清单）

facade 只允许依赖以下接口；新增依赖需修订本节。完整盘点见附录 B。

### 3.1 libeasynet_cli C ABI v3（`EasyNet-Cli/include/easynet_cli.h`，15 函数）

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

### 3.5 easynet_axon Python SDK（`EasyNet-Axon/sdk/python`）

- `invocation/axiom.py`：七元组 envelope、`fresh_nonce()`、
  `CausalContext.{none,scalar,list_,merkle}`、Ed25519 签名/验签、
  canonical bytes（RFC-001 §4.2/4.3）。
- `invocation/audit.py`：`InvocationReceipt.verify()/trace()/
  prove_authority()`、`verify_receipt_chain()`。
- `ura.py`：`parse_ura()`、`build_device_ability_ura()`。
- 错误 taxonomy（7 类）。
- **已知缺口**：SDK 层 stream/bidi async 迭代器未定稿 → facade 流式路径
  一律走 C ABI（§3.1），不等 SDK。

### 3.6 拓扑约束

hub 绑 TCP 必须 TLS（Invariant 2，无明文后门）；device 禁绑 TCP、只出不
进（Invariant 1）；hub 统一已落地（EasyNet-Cli `f96bc02`，2026-06-05），
daemon SDK 已落地（`88bbd86` / `7ea78eb`）。

---

## 4. 架构

```
┌─────────────────────────────────────────────────────────────┐
│  easyremote v2（纯 Python facade，目标 ~2.5k LOC）            │
│                                                              │
│  client.py     Client / AsyncClient / @remote / Stream       │
│  node.py       ComputeNode / RegisteredFunction / AbilityInfo│
│  context.py    Context（服务端组合）                          │
│  gateway.py    Gateway(=Server) → hub daemon 包装             │
│  schema.py     类型注解 → input/output JSON Schema            │
│  pipeline.py   Pipeline / MissionRun → EAL → mission.run      │
│  invocation.py Invocation / PreparedInvocation / Tuple        │
│  receipts.py   Receipt / ReceiptChain（re-export 包装）        │
│  errors.py     8 类异常                                       │
│  config.py     configure() / 发现链 / doctor                  │
│  _transport/   ctypes 绑定 C ABI（私有）                      │
│  _host/        warm 宿主 + 薄转发器（私有）                    │
└──────────────┬─────────────────────────┬─────────────────────┘
               │ 协议对象/签名/URA/回执验证 │ daemon 生命周期 + invoke/stream/bidi
        ┌──────▼──────┐           ┌──────▼──────────┐
        │ easynet_axon │           │ libeasynet_cli  │
        └─────────────┘           └──────┬──────────┘
                                   ~/.easynet/daemon.sock
                              ┌──────────▼──────────┐
                              │   easynet-daemon     │
                              │ device / hub / both  │
                              └─────────────────────┘
```

### 4.1 关键设计决策

**D1 签名策略。** 本地快路径（Local-fast admission）不带
`caller_signature`；跨 hub / federated 路径用 `sign_invocation` +
credentials.json 密钥自动签名。`sign=None` 表示按路径自动判定，
`sign=True/False` 显式覆盖。

**D2 warm 进程（v1 "0ms always-warm" 卖点的存续）。** daemon exec 绑定
现仅 `shell | eal`。两步走：

- 过渡（本期）：ability 以 `exec: shell` 指向薄转发器（编译型小二进制，
  随 wheel 分发）：stdin → 本地 UDS → `_host` 常驻 Python 进程 → 回写。
  每调用只付一次小进程 spawn（~10ms 级），模型常驻显存。
- 净土（Cli PR-1）：external ability host attach 协议——宿主进程经 bidi
  会话挂接 daemon，invocation 直接派发进会话。落地后 `_host` 切换底层，
  facade API 不变。

**D3 负载均衡两阶段安家。** 七元组要求确定的 `callee`：

- Phase 1（本期，零 daemon 改动）：客户端选点——
  `federation.resolve(include_abilities)` 拿候选 → `pick` 策略挑 callee
  → 直调。
- Phase 2（Cli PR-2）：hub 侧 `pool.dispatch` 转发 ability——选点决策以
  子 invocation 出现在回执链上。落地后 `pick="hub"` 启用，客户端策略保留。

### 4.2 分发与运行前置（新增规范）

- **wheel 按平台捆绑 `libeasynet_cli` 预编译库**（macOS arm64/x86_64、
  linux x86_64/aarch64、win64），加载顺序：`EASYNET_CLI_LIB` 环境变量 →
  wheel 内置 → 系统路径。ABI 版本握手：`easynet_abi_version() == 3`，
  不匹配抛 `Unavailable(reason="abi_mismatch")`。
- **easynet-daemon 不随 wheel 分发**。client/node/gateway 三角色均要求
  本机有已安装、已 pairing 的 daemon。缺失时报错信息直接给出安装与
  `easynet pair` 命令。
- `easyremote doctor`（CLI 入口）：诊断 lib 加载、control.json、daemon
  存活、credentials、ABI/IPC 版本，输出逐项 ✓/✗。
- 依赖：`easynet_axon`（PyPI），不依赖 grpcio/protobuf（流量走 C ABI）。

---

## 5. SDK 公开接口规范（normative）

### 5.0 产品原则

0. **register 产出的是 capability，capability 的定义就是接口清单。**
   注册后同一函数同时满足三重最小语义：callable（Client / `@remote`）、
   discoverable（MCP 投影 + `discover`，零额外 API）、composable
   （Pipeline 引用 + `Context.call`）。任何让三者不同源的设计被拒绝。
1. **12 行体验不破坏。** 唯一新增前置是一次性 `easynet pair`。
2. **三层渐进暴露。** L0：`register`/`execute`，零协议词汇；L1：选点、
   流、超时；L2：七元组、回执链、causal、签名。每层升级只隔一个属性访问。
3. **Result-first，receipt-always-available。**
4. **错误即 taxonomy**，不发明第 8 类运行期错误。
5. **不留 pickle。** 参数默认 JSON；二进制媒体显式 `content_type` + 流。
6. **sync-first + `.aio` 镜像**，不做双 API 分裂。
7. **facade 零协议发明。**

### 5.1 顶层导出

```python
__all__ = [
    # 三件套（Gateway 为 v2 首选名，Server 永久保留为别名）
    "Gateway", "Server", "ComputeNode", "Client",
    # 调用
    "remote", "Invocation", "PreparedInvocation", "InvocationState",
    # 服务端组合
    "Context",
    # 回执（thin wrapper over easynet_axon.invocation.audit）
    "Receipt", "ReceiptChain", "VerifiedReceipt",
    # 流
    "Stream", "BidiSession",
    # 编排
    "Pipeline", "MissionRun",
    # 错误
    "RemoteError", "Cancelled", "DeadlineExceeded", "Unavailable",
    "InvalidArgument", "ResourceExhausted", "PermissionDenied",
    "InternalError", "SchemaError",
    # 配置
    "configure",
]
```

### 5.2 十二行 hello-world（验收基准，P3 必须原样跑通）

```python
# 1. 网关（任意 VPS；首次运行自动出自签证书，打印指纹 + 节点配对命令）
from easyremote import Gateway
Gateway(port=8443).start()

# 2. 算力节点（你的设备；身份与网关地址来自一次性 easynet pair）
from easyremote import ComputeNode
node = ComputeNode()

@node.register
def ai_inference(prompt: str) -> str:
    return model.generate(prompt)

node.serve()

# 3. 调用方（任何地方）
from easyremote import Client
print(Client().execute("ai_inference", "Hello EasyNet"))
```

与 v1 差异仅两处：`Server(port=8080)` → `Gateway(port=8443)`（TLS 强制；
`Server` 别名仍可用）；节点首次接入前一次性 `easynet pair`。

### 5.3 `Gateway`

```python
class Gateway:
    def __init__(
        self,
        port: int = 8443,
        *,
        realm: str | None = None,                  # None → credentials/默认 realm
        tls: TLSConfig | Literal["self-signed", "acme"] = "self-signed",
        mode: Literal["hub", "both"] = "hub",      # both = 同机 backend 场景
    ): ...

    def start(self, block: bool = True) -> None
    def stop(self) -> None

    @property
    def endpoint(self) -> str            # 对外 TLS endpoint
    @property
    def pairing_command(self) -> str     # 给节点复制粘贴的一行命令
    @property
    def fingerprint(self) -> str         # 自签证书指纹（带外校验）

Server = Gateway   # v1 兼容别名，永久保留
```

语义：包装 `easynet_daemon_start(DaemonStartConfig::hub() JSON)`。
`self-signed` 自动签发、指纹写进 pairing 命令（节点侧 pin）。
**没有明文 HTTP 选项**——facade 不替底座开 Invariant 2 的口子。

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
`build_device_ability_ura(realm, device_id, namespace, fn_name)` 生成。
调用期参数校验在 daemon 侧由 input_schema 执行；facade 客户端做同 schema
的 fail-fast 预检。

**MCP 投影（discoverable，零节点侧 API）：** 注册即投影。daemon 把
ability descriptor 自动投影为 MCP tool spec（`easynet mcp_server` /
`easynet start --mcp`）。facade 不复刻目录；`AbilityInfo.mcp_tool` 仅供
检视。

### 5.5 `Context`（服务端组合——composable 的第一半）

```python
from easyremote import Context

@node.register
def quarterly_report(ctx: Context, quarter: str) -> str:
    rows = ctx.call("teamA.fetch_sales", quarter)   # 跨网络子调用
    ctx.progress({"stage": "summarizing"})
    if ctx.cancelled:
        return ""
    return summarize(rows)
```

```python
class Context:
    invocation_id: str
    caller: str                        # 调用方 URA（问责语义：谁在叫我）

    def call(self, function: str, /, *args,
             node: str | None = None, timeout: float | None = None,
             **kwargs) -> Any
        # 子调用：causal_context 自动挂接当前 invocation 的回执，
        # caller = 本节点 agent。回执链上呈现为 child invocation。

    def invoke(self, function: str, /, *args, **kw) -> Invocation
    def stream(self, function: str, /, *args, **kw) -> Stream

    def progress(self, payload: dict | bytes) -> None
    def recv(self, timeout: float | None = None) -> InboundMessage | None
    @property
    def cancelled(self) -> bool
```

底层映射：Axon `AbilityContext`（invocation_id / emit_progress / inbox /
supervisor）+ daemon `invoke` 系统 ability。`ctx.call` 是 composable 的
服务端兑现：能力像库一样互相调用，每一跳都在回执链上。

### 5.6 `Client` 与 `@remote`

```python
class Client:
    def __init__(
        self,
        gateway: str | None = None,        # None → credentials.json
        *,
        timeout: float = 30.0,
        retry: RetryPolicy | None = None,  # 默认仅对带 retry_after 的
                                           # UNAVAILABLE/RESOURCE_EXHAUSTED 退避重试
    ): ...

    # L0：v1 兼容
    def execute(self, function: str, *args, **kwargs) -> Any

    # L1：选点 / 流 / 超时
    def call(self, function: str, /, *args,
             node: str | None = None,
             pick: PickPolicy | Literal["round_robin", "random",
                                        "resource_aware"] = "round_robin",
             timeout: float | None = None,
             **kwargs) -> Any
    def stream(self, function: str, /, *args, **kw) -> Stream
    def session(self, function: str, /, **kw) -> BidiSession   # context manager

    # L2：完整调用对象
    def invoke(self, function: str, /, *args,
               subject: str | None = None,      # URA；None → callee（可检视默认）
               causal: Receipt | list[Receipt] | None = None,
               sign: bool | None = None,        # None → 按路径自动（D1）
               metadata: dict[str, str] | None = None,
               **kwargs) -> Invocation
    def prepare(self, function: str, /, *args, **kw) -> PreparedInvocation

    # 发现（discoverable 的程序化面）
    def functions(self) -> list[FunctionInfo]   # discover 投影
    def nodes(self) -> list[NodeInfo]           # federation.resolve 投影

    @property
    def aio(self) -> AsyncClient                # 同形 async 镜像（方法名不变）
```

```python
@remote                       # 或 @remote("ai_inference", node="gpu-1", timeout=60)
def ai_inference(prompt: str) -> str: ...      # typed stub，函数体永不本地执行

ai_inference("hi")                    # L0 透明调用
ai_inference.stream("hi")             # L1 流
ai_inference.invoke("hi")             # L2 句柄
await ai_inference.aio("hi")          # async 镜像
```

**参数编码**：默认 `application/json`；`bytes` 参数 + 显式
`content_type=` 走二进制（媒体帧场景）；其余一律 JSON Schema 校验。
**无 pickle 通道。**

### 5.7 `Invocation` / `PreparedInvocation` / 回执

```python
class PreparedInvocation:
    tuple: InvocationTuple        # caller/callee/ability/subject/nonce/causal/args_digest
    def with_subject(self, ura: str) -> "PreparedInvocation"
    def with_causal(self, *receipts: Receipt) -> "PreparedInvocation"
    def send(self) -> Invocation

class Invocation:
    id: str
    state: InvocationState        # 镜像 Axon 九态
    tuple: InvocationTuple        # 七元组永远可读（不变式 2）

    def result(self, timeout: float | None = None) -> Any
    def events(self, from_offset: int = 0) -> Iterator[InvocationEvent]
    def cancel(self, reason: str = "") -> None
    def send(self, payload: dict | bytes, message_id: str | None = None) -> MessageAck

    @property
    def receipt(self) -> Receipt          # 终态回执
    def receipts(self) -> ReceiptChain
    def verify(self, resolver: KeyResolver | None = None) -> VerifiedReceipt
        # None → realm 默认 resolver；底层即 easynet_axon M1/M2/M3

class Receipt:                    # thin wrapper；.raw 暴露 easynet_axon 原对象
    type: str; state: str; timestamp_ms: int; invocation_id: str
    def verify(self, resolver=None) -> VerifiedReceipt
    def trace(self) -> CausalTrace
    raw: "easynet_axon.invocation.audit.InvocationReceipt"
```

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

fetch = pipe.step("teamA.fetch_sales")            # ① 别人的函数：按名字引用
                                                  #    （run 前 discover 预检）
@pipe.step(after=[fetch])
def summarize(rows: list[dict]) -> str: ...       # ② 自己注册的函数

publish = pipe.step(publish_report, after=[summarize])   # ③ @remote stub

run: MissionRun = pipe.run(args={"date": "2026-06-11"})
run.status                       # mission.track 投影
run.cancel()
print(pipe.to_eal())             # 可检视 EAL 源，含强制 provenance 头
                                 # （created_by = 当前用户 URA）
```

语义：编译为 EAL → `mission.run`（args `{source, label}`，返回
`{ok, run_id, run_dir, outputs, meta}`）；每 step 是子 invocation，回执链
完整。**facade 不自建编排运行时**；字符串引用在 `run()` 前 fail-fast 预检。

### 5.10 配置与发现

```python
easyremote.configure(
    credentials: Path | None = None,   # 默认 ~/.easynet/credentials.json
    control: Path | None = None,       # 默认 ~/.easynet/control.json
    library_path: Path | None = None,  # libeasynet_cli 显式路径
)
# 等价环境变量：EASYNET_CREDENTIALS / EASYNET_CONTROL_JSON / EASYNET_CLI_LIB
```

零配置链路：`Client()` → control.json → daemon.sock；身份 →
credentials.json。缺失时报错给出 `easynet pair` / `easynet start` 命令。
CLI 入口：`easyremote doctor`（§4.2）。

### 5.11 async 镜像

`client.aio` 返回 `AsyncClient`：方法名与签名同 `Client`，全部
coroutine；`Stream` 同时实现 `__iter__` 与 `__aiter__`；
`RemoteFunction.aio(...)` 为 coroutine。无独立 async 包。

---

## 6. URA 与数据模型映射（按 ura-discipline：缺口举旗不发明）

| 实体 | canonical 形状（一律 builder 生成） |
|---|---|
| 注册函数 → ability | `build_device_ability_ura(realm, device_id, "er", fn_name)` → `easynet:///r/<realm>/ability/device.<device-id>.er.<fn>` |
| caller | credentials.json 的 agent/user URA |
| subject 默认值 | `= callee`（可检视、可覆盖） |

**待拍板 / spec 缺口：**

1. **namespace `er`**：需 CTO 拍板并记入 RFC-001 §URA 实践注记
   （备选：`fn` / 用户自定义）。
2. **daemon 运行时注册 ability（免重启）**：已 P0 实测，见 §6.2-④。
3. **external ability host attach**：Cli PR-1（§9）。
4. **receipt body URA**：RFC-007/008 在途；facade 只把 receipt 当对象
   暴露，不构造 receipt URA。
5. **节点负载指标**：resource-aware 选点数据源，Cli PR-3（§9）。

### 6.2 P0 实测结论（2026-06-11，daemon v0.64.8 / ABI v3 重建产物）

全链路活体验证**通过**：identity（credentials→device URA）→ 七元组
编码 → C ABI → daemon.sock gRPC → dispatch → 响应解码，`demo.discover`
真调 COMPLETED；集成套件 4/4 绿。逐项钉子：

| # | 结论 | facade 影响 |
|---|---|---|
| ① | 磁盘上的 release dylib 曾是 v1/v2 旧产物（只导出已弃用的 `easynet_ability_invoke` 面）；重建后 17 符号与头文件逐一对齐 | 绑定层已加固：先握手后声明全集，旧库报 `abi_mismatch`/`abi_symbol_missing` + 重建指引 |
| ② | unary 路径 `admission_receipt = null`（此 daemon 版本不返回执摘要） | 回执链验证暂无数据源——强化缺口 4 的优先级；`Invocation.receipt` 正确返回 None |
| ③ | ability URA 实例形状确认：`easynet:///r/localhost/ability/dev.demo.chat`（user.agent.verb 三段 owner） | `FunctionInfo.qualified_name` 透传正确 |
| ④ | **运行时注册不是热生效**：裸投 manifest 目录被 `ROUTE_NEGATIVE / NEGATIVE_REASON_NODATA` 拒绝——agent 必须先经 daemon 注册流程（agents.json）才有 dispatchable route | `ComputeNode.register` 写盘正确但不充分；**新增 Cli 侧 PR-4：agent/ability 运行时注册路径**（或 facade 调用既有注册 ability，待定位） |
| ⑤ | gRPC `FailedPrecondition` 经 C ABI 折叠为 `ERR_ABILITY_FAILED`，daemon 的 ROUTE_NEGATIVE 详情完整保留在 `last_error` 消息中 | 错误映射可用；未注册命名空间报 `INTERNAL/ability_failed` 而非 NOT_FOUND |
| ⑥ | **热注册路径已存在，无需新 Cli PR**：`easynet agent add --type <T> <NAME>`（一次性身份）+ `easynet agent refresh --agent <NAME>`（manifest 热加载，文档原话"without daemon restart"）；agent root 由 daemon 决定并写入 agents.json（实测落在新约定 `agents/` 下） | `ComputeNode` 已接线：root 从 agents.json **读回**而非假设；start()/post-start register 自动 refresh；未注册 namespace 给出 `easynet agent add` 指引。残留小缺口：AgentType 只有 AI-CLI 包装类型（claude-code/codex/codex-app-server），**manifest-only 类型**列为小型 Cli 增强项（替代原 PR-4） |
| ⑦ | **闭环全通**（register→manifest→refresh→daemon→shell executor→forwarder→warm host→结果回传）；shell 执行器结果包络实测：`{fulfilled_by:"shell", exit_code, elapsed_ms, sandboxed, result:"<stdout字符串>"}`，函数真实返回值是 `result` 内的 JSON 文本 | `Invocation.result()` 已按实测形状解包（系统 ability 直接 JSON 不受影响；原始包络保留在 raw_response） |
| ⑧ | warm 路径延迟基线：首调 76ms / 二调 63ms——Python 解释器 forwarder spawn 主导，**未达 §8-P2 的 <50ms 目标**（D2 预测兑现） | 收敛路径不变：编译型转发器（短期）或 Cli PR-1 host-attach（根治）|

---

## 7. v1 → v2 兼容与退役

### 7.1 兼容矩阵

| v1 写法 | v2 行为 |
|---|---|
| `Server(port).start()` | 可用（别名→Gateway）；自动 TLS + 打印指纹 |
| `node.register` / `node.serve()` | 不变 |
| `Client.execute("fn", args)` | 不变（JSON 可表达参数） |
| pickle 参数（自定义对象） | **破坏性变更**：`InvalidArgument`，报错给出 pydantic/二进制流出路 |
| `@remote(node_id=…)` | `@remote(node=…)`；旧参数名保留 ≥1 个 minor 版本 + DeprecationWarning |
| `@remote(load_balancing={…})` | `pick=` 策略映射；不可映射项报错 |
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
| 依赖 | 移除 grpcio/protobuf；新增 easynet_axon + 平台 wheel 内置 libeasynet_cli |

---

## 8. 实施计划（P0–P5）

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **P0 链路验证**（1–2 天） | device daemon + 手写 shell-exec ability + axiom.py 七元组 + C ABI invoke；核实运行时注册路径 | receipt 经 `verify()` 验签通过；运行时注册结论写入本文 §6.2 |
| **P1 `_transport`**（~3 天） | ctypes 封装 15 函数；ABI 握手；错误映射；stream→迭代器、bidi→双队列 | unary/stream/bidi + 超时/取消 pytest 全绿 |
| **P2 节点侧**（~1 周） | `schema.py` 推导；`register` → manifest → deploy；`_host` warm 转发器 | 注册函数可被 `discover` 发现并端到端调用；warm 二次调用 p50 < 50ms |
| **P3 客户端侧**（~1 周） | `execute/call/invoke/prepare/stream/session` + `@remote` + `.aio` + `Context` | §5.2 12 行 demo 原样跑通；receipt 链验证测试；`ctx.call` 子调用出现在回执链 |
| **P4 gateway + 选点**（~1–2 周） | `Gateway` 包装 + 证书引导；客户端 `pick` 策略 | 双节点同名函数按策略分流；TLS 强制下全链路通 |
| **P5 pipeline + 退役**（~1 周） | `Pipeline`→EAL→`mission.run`；执行 §7.2 删除清单 | gallery smoke tests 全绿；wheel 不含 grpcio；v1 兼容矩阵逐项测试 |

阶段间依赖：P1←P0；P2/P3←P1（可并行）；P4←P3；P5←P2+P3。
风险集中在 P0/P2（warm host、运行时注册），故 P0 先行。

---

## 9. EasyNet-Cli 侧配套 PR（独立工作流，不阻塞 P0–P3）

| PR | 内容 | facade 受益点 |
|---|---|---|
| PR-1 | external ability host attach 协议（RFC + 实现） | `_host` 摘掉 shell 转发器，真零 spawn |
| PR-2 | hub `pool.dispatch` 系统 ability | `pick="hub"`，选点上回执链 |
| PR-3 | 节点负载指标进 heartbeat / ability summary | `pick="resource_aware"` 数据源 |

---

## 10. 测试策略

1. **单测**：schema 推导 table-driven（§5.4 表逐行）；错误映射全枚举；
   URA 经 `parse_ura` round-trip（不变式 4）。
2. **集成**：CI 起本地 easynet-daemon（device 模式 fixture），跑
   unary/stream/bidi/取消/超时/`ctx.call` 子调用。
3. **一致性**：每条集成用例断言 receipt 链 `verify_receipt_chain()` 通过
   （论文 claim 的工程化守门）。
4. **兼容**：§7.1 矩阵逐行用例；§5.2 12 行 demo 作为 e2e 冒烟。
5. **性能基线**：warm 路径 p50 < 50ms、p99 < 150ms（本机 daemon）；
   回归即 fail。
6. **gallery**：现有 `gallery/run_smoke_tests.py` 迁移后全绿为 P5 出口。

---

## 11. 风险

| 风险 | 缓解 |
|---|---|
| daemon 无免重启注册路径 | P0 探明；最坏并入 PR 清单，P2 临时用重启注册 |
| warm 转发器 spawn 开销超预算 | 转发器用编译型二进制；PR-1 为根治 |
| axon Python SDK stream 包装未定稿 | 流式一律走 C ABI（§3.5），不依赖 SDK 进度 |
| hub TLS 提高上手门槛 | self-signed + pairing 命令内嵌指纹；`doctor` 诊断 |
| 平台 wheel 构建矩阵成本 | 复用 EasyNet-Cli 现有交叉编译产物；首版可只发 mac/linux |

---

## 12. 开放问题（待 CTO 拍板）

1. namespace `er`（§6.1）。
2. `Gateway(tls="acme")` 进首版，还是先 self-signed + pin。
3. v1 兼容层保留几个 minor 版本。
4. PyPI 沿用 `easyremote`（major bump 2.0）还是新包名。

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
> Client().execute("ai_inference", "hello")
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

### B.1 libeasynet_cli C ABI v3（15 函数）

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
- `DaemonStartConfig`：`device(node_id)` / `hub()` / `with_realm` /
  `with_env` / `with_log_path` / `detached` / `start()`；`DaemonMode =
  Device | Hub | Both`。
- 约束：hub TCP 必须 TLS；device 禁绑 TCP；SIGHUP 仅热载 federated_peers
  与 quota。

### B.3 easynet_axon Python SDK

- `Client.tenant().ability().principal().call()`；`Transport` 协议；
  `SidecarTransport` / `DendriteBridge`（FFI 级 unary/stream/bidi）。
- `invocation/axiom.py`：`InvocationEnvelope`、`AgentIdentity` /
  `SubjectIdentity`、`CausalContext.{none,scalar,list_,merkle}`、
  `fresh_nonce`、`canonical_invocation_bytes`、`sign_invocation` /
  `verify_invocation_signature`、`sign_receipt` / `verify_receipt_signature`、
  `KeyResolver` / `FileKeyResolver`、`AuthorityBinding`、`DelegationProofBody`。
- `invocation/audit.py`：`InvocationReceipt`（M1 `verify` / M2 `trace` /
  M3 `prove_authority`）、`verify_receipt_chain`、`AxiomBinding`。
- `invocation/handle.py`：`InvocationHandle`、`EventStream`（可续传）、
  `InvocationState` 九态。
- `invocation/supervisor.py` / `messaging.py`：`Supervisor`（进程组隔离、
  资源限额、清理保证、orphan reap）、`MessageInbox`（FIFO、幂等、有界）。
- `invocation/local_runtime.py`：`LocalRuntime`（参考运行时）、
  `AbilityContext`。
- `ura.py`：`parse_ura`、`build_device_ability_ura`、`ParsedURA/ParsedAbility`。
- `errors.py` / `invocation/error.py`：12 类 SDK 级 + 7 类 invocation 级。
- federation 六件套 wire shape：`sdk/FEDERATION_INVOKE_SCHEMAS.md`。
- 缺口：SDK 层 stream/bidi async 迭代器、async connect/close 未定稿。
