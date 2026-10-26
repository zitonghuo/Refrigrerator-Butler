# 安全说明

## 关于 AppID 告警

`wx8afbc664265f1bc0` 是微信小程序的 **AppID（公开标识）**，会随小程序包分发，任何人都能看到。它本身不能调用接口、不能读取数据，**不是密钥**。

如果 GitHub 的 Secret scanning 对 AppID 报警，可以在仓库的 **Security → Secret scanning → 对应告警 → Dismiss → False positive** 关闭，备注：

> WeChat Mini Program AppID is a public identifier. AppSecret is not stored in this repository.

## 仓库里没有的内容

- 小程序 **AppSecret**（只在微信公众平台后台，从不写入仓库）
- 云开发密钥、OCR / 识别服务令牌
- GitHub 个人令牌、私钥、`.env`

所有令牌都通过**云函数环境变量**或**容器环境变量**注入：

| 变量 | 位置 |
| --- | --- |
| `EXPECTED_APPID` | `fridgeApi` 云函数环境变量（可选，默认值只是 AppID） |
| `OCR_URL` / `OCR_TOKEN` | 云函数环境变量，对接私有 OCR 服务 |
| `VISION_URL` / `VISION_TOKEN` | 云函数环境变量，对接私有食材检测服务 |
| `FRIDGE_VISION_TOKEN` | 识别容器环境变量（开发调试时不设置） |

## 为什么仓库里还保留 AppID

- `app/project.config.json`：微信开发者工具导入工程必需
- `app/miniprogram/config.js`：发布检查用它和工程配置做一致性校验
- `app/cloudfunctions/fridgeApi/index.js`：作为 `EXPECTED_APPID` 默认值，拒绝其它小程序调用本云函数

这几处是设计需要，不是泄露；文档和 `release.json` 里的重复值已经移除。

## 真的发生泄露时

1. **AppSecret**：微信公众平台 → 开发管理 → 开发设置 → 重置 AppSecret
2. **云函数令牌**：控制台更新环境变量并重新部署
3. **令牌进入了 Git 历史**：用 `git filter-repo` 清理后强推，并立即轮换令牌（只删文件不轮换是不够的）
4. **小程序代码包里的密钥**：小程序包可被反编译，任何长期密钥都不能放在客户端；本项目客户端的 `visionUrl` 仅用于本机开发，发布前清空

## 报告问题

发现仓库内包含真实密钥或凭据，请开 GitHub Issue 说明位置（不要贴出密钥本身），或私下联系维护者。
