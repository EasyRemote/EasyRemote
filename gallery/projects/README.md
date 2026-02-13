# Gallery Projects Index

Author: Silan Hu (silan.hu@u.nus.edu)

## 目标

把历史上有教学价值但已清理的示例，重建为“可运行的小项目模板”，用于快速上手。

## 项目列表

- `00_basic_remote_math`
  - 对应历史基础示例（server + compute node + client）
- `01_team_gpu_pool_load_balancing`
  - 对应历史多节点负载均衡示例
- `02_mcp_tool_mesh`
  - 对应历史 MCP 工具网关类示例
- `03_a2a_incident_copilot`
  - 对应历史多 Agent 协作/运维处置类示例
- `04_function_marketplace`
  - 对应函数市场（K5）示例
- `05_local_data_residency_ai`
  - 对应本地数据不出域（K6）示例

## 统一规则

- 所有项目均对齐当前 EasyRemote API。
- 每个目录自带 `README.md` 和入口脚本。
- 每个目录均提供 `Makefile` 一键命令（`make help` 查看）。
- 代码采用 OOP 组织，便于复制到真实业务仓库。
- 可用 `uv run python gallery/run_smoke_tests.py` 对现有应支持案例做全量冒烟测试。
