# Vela 项目续接档案（可用于新对话）

> 这是开发连续性记录，不包含管理员 Telegram ID、Bot Token、任何真实节点/域名/IP、证书、数据库或私密配置。**本文件随每个阶段代码包一起保存。**

## 1. 永久约定

- 产品名：**Vela**。Telegram Mini App、Vela Bot、控制中心和未来 `vela` 维护命令都使用这一品牌；蓝色系 APP 标志已纳入 `brand/` 和 `frontend`。
- 唯一目标 Fork：**`smgsp6/3x-ui`**；上游 **`MHSanaei/3x-ui`**，保留 GitHub Fork 关系。**不改仓库名称，不改 Go 模块路径 `github.com/mhsanaei/3x-ui/v3`，不触碰其他仓库。**
- Telegram 官方 Mini App（WebView + Telegram SDK），**不要实现或启用独立 HTML Widgets**。
- 原版功能尽量完整保留；改造主要在独立模块和发行层，减少上游冲突。
- 公开仓库、CI 构建和镜像不得包含个人 Token、证书私钥、数据库、真实服务器/节点/用户资料或备份；服务器数据应只存本地。
- 后续升级必须 **审查上游改动 → 审核 PR → 构建测试 → 签名发布 → 备份 → 分批更新 → 故障恢复**。禁止直接运行原作者可变 `update.sh` 来更新 Vela。
- 用户希望最终一键 Docker 安装与 `vela update`，但**在真实测试 VPS、Telegram、证书与节点验收前不得标为可正式部署**。

## 2. 当前交付物

- 最新开发预览：本目录对应 **Vela 第十二阶段**；若需要源文件，解压对应 `vela-phase12-dev-preview.zip`。
- `apply_to_repo.py`：只接受用户 Fork、固定已审计 commit `5297fd3c8495d80fab97ae511553fa545c69e913`、非默认分支、干净工作树，`--check` 只预览，失败恢复原文件。
- `internal/web/service/tgminiapp/`：Telegram initData 签名、管理员数值白名单、只从本地 Secret 读 Token、证书状态元数据。
- `internal/web/controller/miniapp.go`：Mini App 登录、内部健康检查、证书只读接口。
- `frontend/src/`：Logo、启动页、移动导航、独立证书页面（目前只读）。
- `deploy/vela/vela`：本地运维命令（status/logs/doctor/backup/update/recover）；未配置正式发布公钥，因此 update **故意拒绝生产更新**。
- `deploy/vela/privacy_audit.py`、`git_history_audit.py`：离线隐私扫描；GitHub Actions 只读审查方案在 `.github/workflows/`。
- 本阶段新增：**签名发行序号防重放**。签名清单必须含正整数 `releaseSequence`；安装器必须初始化本机 `release.sequence`，它记住单调版本，已审核旧清单不能轻易被重复用于自动降级；回滚日志保存升级前序号。

## 3. 已验证 vs. 未验证

### 已验证（离线开发环境）

- Go 标准库隔离的 Telegram/证书单元测试、Race 和 vet（前序阶段记录）。
- Docker 维护脚本模拟升级、故障回滚、断电恢复、密钥签名拒绝等（前序阶段）。
- Python 脚本的语法与针对性测试；**以本阶段实际测试报告为准**，不要把模拟测试描述成真实 Docker 验收。
- 特定 Fork HEAD 的 GitHub 只读核对，仓库数据并未被写入或发布。

### 未验证 / 发布阻断项

1. 整仓 Go 1.27.4 / Node 26 React/Vite 构建、类型检查、全部 CI；本地版本与依赖不满足要求。
2. 真正 Docker 镜像构建、镜像层隐私扫描、Docker Host Network / NET_ADMIN / fail2ban 安全测试。
3. Telegram WebView/真实 Bot 登录、CSRF、cookie、CSP 与非管理员访问测试。
4. 证书上传／配置／续签／Telegram 到期告警；已有证书只读检查、可选到期提醒及面板 Go HTTPS 热加载（不负责签发续签）。
5. 实际多节点、Xray 动态 TCP/UDP 端口、订阅、API、客户端全功能集成回归。
6. 正式 Ed25519 签名密钥与发行公钥指纹、稳定镜像及 `stable.json`，镜像 Digest 不可变。
7. 真正安装器、一键安装、防火墙、HTTPS 反代配置、SQLite 一致性恢复和分批升级。
8. Git 全历史、公开镜像和 GitHub Actions 日志检查的完整隐私审计。
9. GitHub 写入连接此前返回 403；**没有将开发包推送到用户仓库**。

## 4. 代码使用方法（仅开发审查）

```bash
# 在本阶段代码包解压目录运行：
GO111MODULE=off go test -race ./internal/web/service/tgminiapp
python3 -m unittest discover -s tests -v
bash -n deploy/vela/vela
sha256sum -c SHA256SUMS

# 在用户自己 Fork 的独立 feature 分支、指定已审计 HEAD 中：
python3 /path/to/vela-phase12/apply_to_repo.py . --check
# 确认差异后再应用；不可对 main 直接应用
python3 /path/to/vela-phase12/apply_to_repo.py .
```

> 严禁将含真实数据的运行目录复制到公开 Git 仓库或打包为交付 ZIP；运行时的 `/opt/vela` 与公开源码树必须物理分开。当前项目不是生产安装包。

## 5. 如果必须换 ChatGPT 对话

将**最新 `vela-phase12-dev-preview.zip`** 和本文件上传，并对下一段对话说：

> 继续开发我的 Vela 项目。唯一仓库 smgsp6/3x-ui，不改仓库名与 Go 模块路径，不触碰其他仓库。请先读取 docs/PROJECT-CONTINUITY.md 和现有源码，继续修复和真实集成，不要重新规划或承诺后台执行。禁止发布任何个人 Token、证书、数据库或服务器数据。旧包不代表生产可安装。

这套方法让关键决定随文件保存，不依赖单个聊天窗口的长度。

## 6. 第九阶段附加进度

- `certificate_alerts.go` 新增**默认关闭**的 Telegram 私聊证书提醒（09:00，每个到期阶段只提醒一次，提醒内容不含域名/IP/路径）。
- 新增的 `XUI_TG_CERT_ALERT_ENABLED=true` 必须由服务器操作者主动开启；通知会发送文字给 Telegram 服务。
- `screen_view.go` 的 Mini App 按钮只显示在已授权管理员的私人聊天中；证书管理页面显示提醒状态。
- 请以 `docs/PHASE9-CHANGELOG.md` 和第九阶段实际测试输出为准。仍不能生产安装。

## 7. 第十阶段新增进度

- 修正证书状态接口 JSON 结构：`obj.certificates` 与 `obj.alertsEnabled`；修复通用 `HttpUtil` 丢弃顶层提醒状态造成页面误报的问题。
- `tls_reloader.go` 在 Vela 直接 HTTPS 模式下通过 `tls.Config.GetCertificate` 热加载有效新证书：30 秒限速、有效期和配对检查、拒绝证书到期日倒退，保留最后可用证书，不传输私钥；原版 TLS 逻辑仅在 Vela 模式开启后才新增回调。
- `tls_reloader_test.go` 含本地实握手（无 SNI）、半成品证书拒绝、过期/未来/到期日倒退拒绝、并发 Race；`tests/test_certificate_contract.py` 校验证书 API 与前端数据结构；补丁临时文件写入已加独占、无符号链接跟随保护。
- 仍不拥有生产签名镜像，没有实际 Telegram/Docker/整仓 Go+React 构建或 ACME 真实续签验收；**绝不能将开发包标记为可正式安装**。

- 第十阶段本次离线结果：37 项维护 + 9 项补丁 + 3 项证书契约 + 9 项隐私 + 3 项历史扫描，合计 **61 项 Python 测试通过**；Go Race 连续五次通过，真实 Docker/Telegram/整仓构建未通过验收。

## 8. 第十一阶段新增进度

- 由于当前 Fork 不追踪 `internal/web/dist` 但 Go 使用 `//go:embed all:dist`，将 CI 调整为前端构建后才执行完整 Go 测试；加入干净环境 Docker 构建任务（仅在隐私审计、完整代码和维护测试通过后运行，不推送）。镜像构建后会在 CI 直接扫描每层中是否意外含密钥或数据库，无镜像上传。尚没有拿到真实 GitHub CI 日志，不能算构建完成。
- 在 Vela 模式封堵原版 Bot 将 SQLite 数据库和 Xray 私密配置上传至 Telegram 的已发现入口：自动、手动、API 和底层文件发送；本地备份不受影响。其他已授权的 Bot 消息/通知仍会使用 Telegram 网络。
- Vela 配置 TLS 却无法加载证书或私钥时禁止静默回退 HTTP；无面板 TLS 时可使用经 HTTPS 反向代理保护的 loopback HTTP。
- 修复重复 `modify()` 调用会覆盖同一路径先前修改的问题，添加回归测试。
- 继续坚持不改 `smgsp6/3x-ui` 仓库名及 Go 模块，不上传真实私人数据。

## 9. 第十二阶段新增进度

- `tgminiapp.BotToken()` 强制检查本地 Secret 文件模式、父目录权限、已打开文件与 Lstat inode 相同，以及单行内容，防止绕过安装器造成 Token 意外可读或被替换；测试加入了 0644、0660、危险父目录、换行和 NUL 用例。
- Go TLS 热加载器强制保留当前证书的原有 DNS 和 IP SAN，不能自动换成其他域名；手动改变域名须经明确运维审查和重启。
- GitHub 只读检查 22 个上游修改目标的关键锚点均存在且唯一；但未能获取完整仓库进行整仓 Go/React/Docker 编译。
- 项目仍为开发预览，GitHub 未写入，生产签名密钥和发布镜像仍未建立。

- 第十二阶段实际离线结果：原有 73 项 Python 测试和新 3 项契约测试分别运行，通过 **76/76**；Go 独立安全模块 Race 和 vet 通过。见 `docs/PHASE12-TEST-REPORT.md`。完全没有验证真实 Docker 和 Telegram。
