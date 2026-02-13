# 02 MCP Tool Mesh

Author: Silan Hu (silan.hu@u.nus.edu)

## 场景

恢复原先 Agent 工具网关类案例，以可运行项目形式提供。

## 文件

- `runtime.py`: 协议 runtime（能力发现 + 工具执行）
- `run_demo.py`: MCP 请求演示入口

## 运行

`uv run python gallery/projects/02_mcp_tool_mesh/run_demo.py`

## 一键命令

- `cd gallery/projects/02_mcp_tool_mesh && make help`

## 覆盖协议行为

- `initialize`
- `tools/list`
- `tools/call`
- batch request + notification request
