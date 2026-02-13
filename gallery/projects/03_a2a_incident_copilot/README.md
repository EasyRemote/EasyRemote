# 03 A2A Incident Copilot

Author: Silan Hu (silan.hu@u.nus.edu)

## 场景

恢复原先“多 Agent 协作/运维处置”教学价值，以 A2A 协议项目形式提供。

## 文件

- `runtime.py`: 任务执行 runtime
- `run_demo.py`: A2A 请求演示入口

## 运行

`uv run python gallery/projects/03_a2a_incident_copilot/run_demo.py`

## 一键命令

- `cd gallery/projects/03_a2a_incident_copilot && make help`

## 覆盖协议行为

- `agent.capabilities`
- `task.execute`
- `task.send` notification
- batch request
