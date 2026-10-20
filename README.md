# 小满冰箱 / 冰箱管家

家庭食材管理项目：拍照或手动录入食材，跟踪临期，家庭共享库存与采购清单。

最终交付形态是**微信小程序**，采用微信云开发（云函数 + 云数据库），不需要自己准备服务器和 HTTPS 域名。仓库里同时保留了一套早期本地演示版和一个可选的食材识别服务。

## 仓库结构

```text
app/            正式交付：微信云开发版（11 页小程序 + 云函数 + 可选 OCR 容器）
vision/         食材识别服务（YOLOv8，可选，可部署成 HTTPS 供云函数调用）
local-demo/     早期本地演示版（Python 后端 + 浏览器页面 + 单页小程序，保留参考）
docs/           项目文档与需求参考图
```

## 快速开始

### 正式版（微信云开发）

1. 用微信开发者工具导入 **`app/`** 目录（不要只导入 `app/miniprogram/`）
2. 开通/确认云开发环境，环境 ID 与 `app/miniprogram/config.js` 的 `cloudEnv` 一致
3. 创建 4 个数据库集合并设为禁止客户端读写
4. 上传部署 `cloudfunctions/fridgeApi`（云端安装依赖）
5. 编译，用微信登录，创建或加入家庭

详细步骤见 [`app/README.md`](app/README.md)、[`app/docs/云开发部署.md`](app/docs/云开发部署.md)。
附件、包装 OCR 与食材检测需要额外部署，见 [`app/docs/摄像与识别部署.md`](app/docs/摄像与识别部署.md)。

### 本地演示（旧版，可选）

```powershell
.\local-demo\start.bat
```

浏览器打开 http://127.0.0.1:8765。说明见 [`local-demo/README.md`](local-demo/README.md)。

### 识别服务（可选）

```powershell
cd vision
.\.venv\Scripts\python.exe -m food_recognition.server --host 127.0.0.1 --port 8770 --device auto
```

说明见 [`vision/README.md`](vision/README.md)；与小程序/云函数的接入方式见
[`app/docs/摄像与识别部署.md`](app/docs/摄像与识别部署.md) 和 [`docs/小程序接入识别服务.md`](docs/小程序接入识别服务.md)。

## 文档

| 文档 | 内容 |
| --- | --- |
| [`app/README.md`](app/README.md) | 云开发版功能、账号与数据规则、目录 |
| [`app/docs/云开发部署.md`](app/docs/云开发部署.md) | 环境、集合、云函数、发布检查 |
| [`app/docs/摄像与识别部署.md`](app/docs/摄像与识别部署.md) | 附件存储、包装 OCR、食材检测 |
| [`app/docs/小满冰箱使用手册.md`](app/docs/小满冰箱使用手册.md) | 面向用户的操作说明 |
| [`app/docs/发布与真机验收.md`](app/docs/发布与真机验收.md) | 提审前检查项 |
| [`app/验证记录.md`](app/验证记录.md) | 云端联调与测试记录 |
| [`docs/小程序接入识别服务.md`](docs/小程序接入识别服务.md) | 为什么模型不放进小程序、如何接 |
| [`local-demo/验收记录.md`](local-demo/验收记录.md) | 本地演示版验收记录 |

`docs/01.png`、`docs/02.png` 是原始需求参考图。

## 当前状态

- **云开发版**：11 页小程序，已部署到 `cloud1-d1guygnthc98774ff`；开发者工具已用真实微信身份完成登录、创建家庭、添加食材和回读。未完成手机真机、双微信账号隔离、隐私保护指引、备案和审核。
- **识别**：云函数支持 `OCR_URL`（包装文字）和 `VISION_URL`（食材检测）两个可选扩展点，结果都只返回候选、由用户确认后入库。两个服务都未部署，未做真机验证。
- **本地演示版**：Python 后端集成测试 12 项（11 通过、1 项因缺少 FFmpeg 跳过）。
- **发布门槛**：`app/release.json` 中真机、双账号、隐私、备案等验证项仍为 `false`，`npm run check:release` 会失败，这是有意设置的门槛。

## 数据与文件

- 云开发版数据存在云数据库；本地演示版数据在 `local-demo/data/fridge.db`（不纳入 Git）。
- 模型权重（约 520 MB）、训练数据集（约 5 GB）和训练产物不在仓库内；数据集已移到 `E:\fridge-keeper-datasets\`，恢复方式见 [`vision/README.md`](vision/README.md)。
- 仓库不包含任何密钥；OCR/识别的令牌只通过云函数或容器环境变量注入。

## 开发与检查

```powershell
# 云开发版：业务/客户端/媒体测试 + 页面与规则静态检查
cd app
npm ci
npm test

# 本地演示版：后端集成测试
python local-demo/tests/test_api.py

# 识别服务
cd vision
.\.venv\Scripts\python.exe -m pytest -q
```
