# 00 Basic Remote Math

Author: Silan Hu (silan.hu@u.nus.edu)

## 场景

最小可运行项目，对应被清理前的 `basic` 测试思路。

## 文件

- `server.py`: 启动网关
- `compute_node.py`: 注册并暴露函数
- `client.py`: 调用远程函数

## 运行步骤

1. 终端 A: `uv run python gallery/projects/00_basic_remote_math/server.py`
2. 终端 B: `uv run python gallery/projects/00_basic_remote_math/compute_node.py`
3. 终端 C: `uv run python gallery/projects/00_basic_remote_math/client.py`

## 一键命令

- `cd gallery/projects/00_basic_remote_math && make help`
