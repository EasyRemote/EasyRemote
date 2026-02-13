# 05 Local Data Residency AI

Author: Silan Hu (silan.hu@u.nus.edu)

## 场景

本地数据不出域（K6）：原始敏感数据留在本地节点，仅输出脱敏结果和风险评分。

## 文件

- `server.py`: 网关（8083）
- `node_local_processor.py`: 本地合规处理节点
- `client.py`: Human 路线调用
- `runtime.py`: Agent 路线 runtime
- `protocol_demo.py`: MCP + A2A 协议演示

## 快速运行

### Human 路线

1. `uv run python gallery/projects/05_local_data_residency_ai/server.py`
2. `uv run python gallery/projects/05_local_data_residency_ai/node_local_processor.py`
3. `uv run python gallery/projects/05_local_data_residency_ai/client.py`

### Agent 路线

`uv run python gallery/projects/05_local_data_residency_ai/protocol_demo.py`

## 一键命令

- `cd gallery/projects/05_local_data_residency_ai && make help`
