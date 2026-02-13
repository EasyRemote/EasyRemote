# EasyRemote Killer Apps Gallery

Author: Silan Hu (silan.hu@u.nus.edu)

## 栏目定位

`gallery/` 专门展示真实业务可落地场景，不写空泛概念，不写无法跑通的伪案例。

分层视角：
- Agent 路线：MCP/A2A 协议接入。
- Human 路线：Decorator（`@node.register` + `@remote`）接入。

## 杀手应用清单（总览）

| 编号 | 杀手应用 | 目标用户 | 当前阶段 | Agent 路线 | Decorator 路线 |
|---|---|---|---|---|---|
| K1 | 私有 AI 推理中台（Team GPU Pool） | AI 团队/研发组 | 已可落地 | MCP tools/call | 远程函数调用 + 负载均衡 |
| K2 | Agent 工具网关（企业内部 Tool Mesh） | Agent 平台团队 | 已可落地 | MCP tools/list + tools/call | 函数注册与执行后端 |
| K3 | A2A 运维处置网络（Incident Copilot） | 平台运维/SRE | 已可落地（短任务） | A2A task.execute/task.send | 运维脚本函数化 |
| K4 | Demo 即服务（Demo-as-API） | 产品/售前/创业团队 | 已可落地 | MCP/A2A 统一入口 | Decorator 快速发布 |
| K5 | 组织内函数市场（Function Marketplace） | 中台团队 | 已可落地（基础版） | capabilities/tools 列表发现 | 注册中心 + 负载调度 |
| K6 | 本地数据不出域的 AI 数据处理 | 医疗/金融/政企 | 已可落地 | MCP/A2A 任务入口 | 本地节点执行 + 远程调用 |
| K7 | 长任务多 Agent 协作工厂 | Agent 工作流平台 | 路线图 | 需要 A2A 状态机增强 | 需要任务状态抽象 |
| K8 | MCP 资源知识网络（Resources/Prompts） | 知识中台/Agent 平台 | 路线图 | 需要 MCP resources/prompts | 需要 schema 与资源映射 |

## 阅读方式

- 总体策略与能力边界：`docs/zh/CORE_USE_CASES_AND_ROUTES.md`
- 详细杀手应用说明：`gallery/killer_apps.md`
- 当前可运行示例：`examples/README.md`
- 项目化快速上手模板：`gallery/projects/README.md`

## 环境准备（uv）

1. `uv sync`
2. `uv run pytest -q`

## 项目化上手（从已清理示例中重建）

- `gallery/projects/00_basic_remote_math`
- `gallery/projects/01_team_gpu_pool_load_balancing`
- `gallery/projects/02_mcp_tool_mesh`
- `gallery/projects/03_a2a_incident_copilot`
- `gallery/projects/04_function_marketplace`
- `gallery/projects/05_local_data_residency_ai`

## 全量案例自检

- 运行：`uv run python gallery/run_smoke_tests.py`
- 或：`cd gallery && make smoke`
- 报告：`gallery/SMOKE_TEST_REPORT.md`
