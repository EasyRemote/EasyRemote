# 01 Team GPU Pool Load Balancing

Author: Silan Hu (silan.hu@u.nus.edu)

## 场景

恢复原先“多节点负载均衡”教学价值，但完全对齐当前 API。

## 文件

- `server.py`: 网关（8081）
- `node_gpu_alpha.py`: 节点 A（暴露 `train_model`）
- `node_gpu_beta.py`: 节点 B（暴露同名 `train_model`）
- `client.py`: 负载均衡调用方

## 运行步骤

1. 终端 A: `uv run python gallery/projects/01_team_gpu_pool_load_balancing/server.py`
2. 终端 B: `uv run python gallery/projects/01_team_gpu_pool_load_balancing/node_gpu_alpha.py`
3. 终端 C: `uv run python gallery/projects/01_team_gpu_pool_load_balancing/node_gpu_beta.py`
4. 终端 D: `uv run python gallery/projects/01_team_gpu_pool_load_balancing/client.py`

## 一键命令

- `cd gallery/projects/01_team_gpu_pool_load_balancing && make help`
