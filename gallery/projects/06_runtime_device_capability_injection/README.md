# 06 Runtime Device Capability Injection

Author: Silan Hu (silan.hu@u.nus.edu)

## 场景

服务端有很多 agentbot。用户设备初始并没有“拍照/录视频”远程服务。  
agentbot 先远程调用用户设备上的安装入口函数，把新能力作为 skill payload 下发并注册到本地节点，再直接调用这些新函数。

对应 Killer App：**K9 远程设备能力注入（Camera/Video as a Runtime Service）**。

## 文件

- `server.py`: 网关（默认 8084）
- `user_device_node.py`: 用户设备节点（含动态技能安装入口）
- `agent_client.py`: 服务端 agentbot 编排脚本（安装能力 + 调用能力）

## 快速运行

1. `uv run python gallery/projects/06_runtime_device_capability_injection/server.py`
2. `USER_ID=demo-user uv run python gallery/projects/06_runtime_device_capability_injection/user_device_node.py`
3. `TARGET_USER_ID=demo-user uv run python gallery/projects/06_runtime_device_capability_injection/agent_client.py`

默认情况下，agent 通过 `TARGET_USER_ID` 定位带有 `user:<id>` capability 的远程节点。  
如果你已经知道具体节点，可直接传 `TARGET_USER_NODE_ID` 覆盖定位。

该项目网关默认启用了流式限流参数（`max_total_active_streams=128`、`max_streams_per_node=8`），避免节点层压力失控。

新增：下发 skill 后，agent 会先调用 `user.camera.list_devices` 探测用户机器可用摄像头索引，再执行拍照。

## 安全与授权（Demo 默认放宽）

该 Demo 的用户设备节点会开启 `allow_transferred_code=True`（允许下发 runtime 代码模块并 `exec` 加载），并默认 `EASYREMOTE_AUTO_CONSENT=1` 自动同意需要授权的能力安装。  
生产环境建议：

- 禁用自动同意（`EASYREMOTE_AUTO_CONSENT=0`），由用户软件/UI 显式确认。
- 为 skill payload 加签或校验来源，并对 runtime 模块设置更严格的大小/数量限制与隔离执行策略。

## 诊断与回退（sandbox 缺失）

用户节点可选加载本地 sandbox actions（`LOAD_SANDBOX_ACTIONS=1`），但 sandbox 目录可能不存在。
此时节点会通过 CMP 状态端点返回诊断信息，agent 可据此决定是否重新下发能力（例如改走 runtime code transfer）。

- 状态端点：`device.get_capability_host_status`

## 摄像头实拍参数

- `PHOTO_SOURCE`: 例如 `front-camera`、`rear-camera`、`camera://0`、`camera://1`、`auto`
- `PHOTO_RESOLUTION`: 例如 `1280x720`、`1920x1080`
- `CAMERA_SCAN_MAX_INDEX`: 摄像头探测最大索引（默认 `4`）
- `CAMERA_FRONT_INDEX` / `CAMERA_REAR_INDEX`: front/rear 对应的摄像头索引
- `CAMERA_CANDIDATES`: `auto` 模式下的候选索引列表（如 `0,1,2,3`）

示例：

`PHOTO_SOURCE=auto CAMERA_SCAN_MAX_INDEX=6 PHOTO_RESOLUTION=1280x720 make client`

## 一键命令

- `cd gallery/projects/06_runtime_device_capability_injection && make help`
