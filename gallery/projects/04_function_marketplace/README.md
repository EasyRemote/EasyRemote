# 04 Function Marketplace

Author: Silan Hu (silan.hu@u.nus.edu)

## 场景

组织内函数市场（K5）：把跨团队函数能力做成可发现、可调用、可治理的目录。

## 文件

- `server.py`: 网关（8082）
- `node_finance.py`: 财务域函数节点
- `node_ops.py`: 运维域函数节点
- `client.py`: Human 路线调用
- `runtime.py`: Agent 路线 runtime
- `agent_catalog_demo.py`: MCP + A2A 目录与调用演示

## 快速运行

### Human 路线

1. `uv run python gallery/projects/04_function_marketplace/server.py`
2. `uv run python gallery/projects/04_function_marketplace/node_finance.py`
3. `uv run python gallery/projects/04_function_marketplace/node_ops.py`
4. `uv run python gallery/projects/04_function_marketplace/client.py`

### Agent 路线

`uv run python gallery/projects/04_function_marketplace/agent_catalog_demo.py`

## 一键命令

- `cd gallery/projects/04_function_marketplace && make help`
