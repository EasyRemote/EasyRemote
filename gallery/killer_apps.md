# Killer Apps: 落地版清单

Author: Silan Hu (silan.hu@u.nus.edu)

## K1 私有 AI 推理中台（Team GPU Pool）

业务价值：把团队闲置 GPU 变成共享推理池，显著降低云推理成本。

落地路径：
- Agent 路线（MCP）：将推理函数暴露为 `tools/call`，供 Agent 统一调用。
- Human 路线（Decorator）：`@node.register` 暴露推理函数，`@remote` 远程调用。

当前可交付：
- 节点注册、函数调用、基础负载均衡、协议批量/通知请求。

下一步增强：
- 多租户配额、计费、请求审计链路。

项目模板：
- `gallery/projects/01_team_gpu_pool_load_balancing`

## K2 Agent 工具网关（企业内部 Tool Mesh）

业务价值：为内部 Agent 提供统一工具目录和稳定调用入口。

落地路径：
- Agent 路线（MCP）：`tools/list` 发现能力，`tools/call` 执行工具。
- Human 路线（Decorator）：业务函数快速注册到网关，持续对外服务。

当前可交付：
- MCP 标准调用主链（initialize/list/call/ping）。

下一步增强：
- MCP resources/prompts 与权限域策略。

项目模板：
- `gallery/projects/02_mcp_tool_mesh`

## K3 A2A 运维处置网络（Incident Copilot）

业务价值：把排障动作做成 Agent 任务调用链，减少人工切换。

落地路径：
- Agent 路线（A2A）：`agent.capabilities` 能力发现，`task.execute` 处置任务。
- Human 路线（Decorator）：把诊断脚本、修复脚本函数化并挂到节点。

当前可交付：
- A2A 短任务调用、通知请求、错误对象一致性。

下一步增强：
- 长任务状态机与取消语义（queued/running/partial/cancelled）。

项目模板：
- `gallery/projects/03_a2a_incident_copilot`

## K4 Demo 即服务（Demo-as-API）

业务价值：从本地能力快速变成可演示、可调用的线上接口。

落地路径：
- Agent 路线：MCP/A2A 协议入口统一外部调用方式。
- Human 路线：Decorator 三件套（Server/ComputeNode/Client）直接发布。

当前可交付：
- 函数快速上线、跨节点调用、协议入口。

下一步增强：
- SLA 看板、灰度发布、版本治理。

项目模板：
- `gallery/projects/00_basic_remote_math`

## K5 组织内函数市场（Function Marketplace）

业务价值：沉淀可复用函数资产，降低重复开发成本。

落地路径：
- Agent 路线：通过 capabilities/tools 目录暴露可用能力。
- Human 路线：通过 Decorator 把领域能力标准化为可复用函数。

当前可交付：
- 基础目录发现 + 执行路由。

下一步增强：
- 标签治理、评分机制、组织级准入规则。

项目模板：
- `gallery/projects/04_function_marketplace`

## K6 本地数据不出域的 AI 数据处理

业务价值：在合规边界内完成计算，不强制把数据迁移到公有云。

落地路径：
- Agent 路线：A2A/MCP 作为任务入口，不改变数据驻留边界。
- Human 路线：本地节点执行敏感处理函数，远程仅传任务参数与结果。

当前可交付：
- 本地执行 + 远程调度的基础模式。

下一步增强：
- 审计追踪、字段级脱敏、策略引擎。

项目模板：
- `gallery/projects/05_local_data_residency_ai`

## K7 长任务多 Agent 协作工厂（Roadmap）

目标价值：复杂流程下的多 Agent 协同编排和可观测执行。

当前阻塞：
- 需要 A2A 长任务生命周期和回调通道。

## K8 MCP 资源知识网络（Roadmap）

目标价值：把工具调用升级为“工具 + 资源 + 提示”全链路智能协作。

当前阻塞：
- 需要 MCP resources/prompts 能力对齐与标准化测试。
