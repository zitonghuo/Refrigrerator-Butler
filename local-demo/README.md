# 冰箱管家 · 本地演示版（旧版保留）

这是项目早期的本地演示形态：Python 标准库后端 + SQLite + 浏览器页面 + 单页小程序，无需安装 npm 包或第三方 Python 库即可跑通核心库存流程。

**它不是最终交付形态。** 正式版是仓库根目录的 [`../app/`](../app/README.md)（微信云开发，11 页小程序，不需要本地后端）。本目录仅用于本地演示、离线参考和历史验收。

## 运行

在仓库根目录执行：

```powershell
.\local-demo\start.bat
```

或手动：

```powershell
python local-demo/server/app.py
```

浏览器打开 **http://127.0.0.1:8765**。首次使用创建家庭并保存个人恢复码；在“家庭”里取邀请码，另一浏览器或小程序用“加入家庭”共享库存。

关闭终端即停止服务，数据保留。端口被占用可设置 `$env:PORT='8766'`。

## 已实现能力

| 能力 | 浏览器端 | 小程序 |
| --- | --- | --- |
| 创建家庭、邀请成员、恢复码登录 | 有 | 有 |
| 手动批量入库、日期来源确认 | 有 | 有 |
| 照片 / 小票 / 视频识别入口 | 有，需配置识别服务 | 有，需配置识别服务 |
| 冷藏 / 冷冻 / 常温筛选 | 有 | 有 |
| 临期分档与未知日期 | 有 | 有 |
| 消耗、丢弃、盘点剩余量 | 有 | 有 |
| 家庭共享采购清单 | 有 | 有 |
| 操作记录 | 最近 200 条 | 最近 200 条 |
| 固定菜谱匹配 | 有，3 个模板 | 暂未提供 |
| 家庭数据 JSON 导出 | 有 | 暂未提供 |

未实现：微信订阅消息、自动保质期估算、自动盘点匹配、节约周报、纠错学习、成员移除、微信身份登录。请勿把本地演示版描述为已完成全部原始需求。

## 小程序联调

导入本目录的 `miniprogram/`。默认 `baseUrl` 是 `http://127.0.0.1:8765`，`urlCheck:false` 只用于本地开发。

手机上的 `127.0.0.1` 指向手机自己，真机联调需要把 `baseUrl` 改成电脑的局域网地址，并显式监听：

```powershell
$env:HOST='0.0.0.0'
python local-demo/server/app.py
```

该选项会让局域网设备访问服务，不适合作为公网发布方式。

## 识别

不配置服务时，识别任务会明确失败并提示手动录入；演示数据不会冒充识别结果。密钥只放服务端环境变量。

**默认：本地 YOLOv8**。启动时会检查并拉起仓库根目录的 `../vision`：

- `vision/.venv` 已创建
- `vision/weights/yolov8s.pt` 已下载

关闭自动启动：`$env:FRIDGE_DISABLE_LOCAL_VISION='1'`；指定设备：`$env:LOCAL_VISION_DEVICE='0'` 或 `'cpu'`。

**可选一：Chat Completions 兼容视觉服务**

```powershell
$env:VISION_URL='完整 chat completions 接口地址'
$env:VISION_MODEL='视觉模型名称'
$env:VISION_KEY='服务端密钥'
python local-demo/server/app.py
```

适配器在 `server/vision.py`。照片、小票、视频素材会发送到该服务；视频先本地抽帧（前 30 秒、每 3 秒一帧、最多 10 帧、宽 960），依赖 FFmpeg（可用 `FFMPEG_PATH` 指定）。

**可选二：自定义识别服务**

设置 `RECOGNITION_URL` 和可选 `RECOGNITION_KEY`，优先于前两种。请求：

```json
{"kind":"photo","images":["不含 data URL 前缀的 base64 图片"]}
```

`kind` 为 `photo`、`receipt` 或 `video`；响应：

```json
{"candidates":[{"name":"番茄","quantity":null,"unit":"个","location":"冷藏","expiry":""}]}
```

数量不确定返回 `null`，日期不确定返回空串；最多 50 项。用户确认后才写库存。

## 数据与业务规则

- 数据库：`local-demo/data/fridge.db`，可用 `FRIDGE_DB` 覆盖。
- 每次入库创建独立批次，同名食材不自动合并。
- 同一提交标识 + 相同内容只入库一次；同标识换内容会被拒绝。
- 消耗/丢弃填减少量；盘点填当前剩余量（可填 0），记录的是变化量。
- 并发更新使用版本号 + 数据库事务，冲突时拒绝旧版本。
- 仅支持同单位数量运算，不换算袋、克等不同单位。
- 日期按中国标准时间当天 23:59:59 判定；分档为已过期、今天到期、3 天内、7 天内、7 天后、日期未知（“今天到期”按到期日当天计算，不是滚动 24 小时）。
- 所有成员权限相同；更换邀请码阻止旧码继续邀请，不移除已加入成员。
- 登录会话默认 30 天过期（`FRIDGE_SESSION_DAYS`）。
- 识别任务默认并发 2 个（`FRIDGE_MAX_TASKS`）；完成/失败任务保留 7 天，幂等记录保留 30 天，启动时自动清理。
- 识别候选带 `confidence`（0–1，未知为 `null`），仍需用户确认后入库。

## 目录

```text
server/app.py        HTTP 接口、数据库、任务处理、库存规则
server/vision.py     可配置视觉服务适配器
web/                 浏览器演示端
miniprogram/         单页小程序（旧版）
tests/test_api.py    后端集成测试
data/                本地数据库（不纳入 Git）
start.bat            Windows 启动脚本
验收记录.md           本地演示版验收记录
```

## 接口速查

除 `/api/auth` 与 `/api/health` 外，请求头带 `Authorization: Bearer <token>`；写接口采用 JSON。

| 方法 路径 | 主要参数 |
| --- | --- |
| GET /api/health | 无需鉴权，版本 / 数据库 / 识别服务状态 |
| POST /api/auth | action=create/join/login 对应 name homeName / invite / code |
| GET /api/state | 家庭、成员、在库批次、采购项、最近操作 |
| POST /api/items/add | key 幂等标识，items 数组 |
| POST /api/items/change | id、version、kind、quantity |
| POST /api/shopping/add、/api/shopping/toggle | name / id |
| POST /api/recognize | kind、data（图片或视频 base64） |
| GET /api/task?id=... | 查询所属家庭的识别任务 |
| POST /api/invite/rotate | 空对象 |
| POST /api/demo | 空对象，仅适用于从未录入库存的家庭 |
| POST /api/logout | 空对象 |

## 测试

```powershell
python local-demo/tests/test_api.py
```

测试使用临时数据库和随机本机端口，不修改真实库存。
