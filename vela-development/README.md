# Vela · Telegram Mini App 服务器管理平台

> [!IMPORTANT]
> 本仓库是 **[smgsp6/3x-ui](https://github.com/smgsp6/3x-ui)** 的个人二次开发版本，基于 [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui)。
> Vela 正在逐步开发。**当前阶段仅实现部分安全登录、证书状态和移动端导航代码；尚未完成全部功能迁移、正式部署或发布。**

## 项目方向

将原版功能完整的 3x-ui 改造成 Telegram 内打开的可视化管理 APP，保留 Go 后端和 Xray-core、数据库与多节点管理能力。

- **正式 Telegram Mini App**：使用 Telegram 官方 WebView / Mini App 机制，不使用聊天内 **HTML Widgets**。Mini App 本身仍依赖 HTML、CSS、JavaScript。
- **精致的 APP 界面**：中文优先、深浅主题、底部导航、手机优先，同时保留复杂配置功能。
- **Telegram 用户验证**：服务器验证官方 `initData` 签名、授权时间和管理员数字 ID 白名单；普通网页登录在 Mini App 模式下禁用。
- **完整原版能力**：服务器、入站、客户端、订阅、节点、路由、出站、DNS、REALITY、日志、备份和恢复等逐步移植，不删减核心功能。
- **独立证书管理**：查看面板与订阅服务的证书、域名、签发者、过期时间、剩余天数和证书/私钥匹配状态；第九阶段新增**可选的私人 Telegram 到期提醒**。第十阶段新增**面板 Go HTTPS 证书热加载**（读取已有续签文件，不负责签发），并修复提醒开关状态显示。独立申请与主动续签仍待完整集成验收。
- **多服务器统一管理**：保留原版节点同步接口，后续增加分批升级、集中告警。
- **Docker 优先部署**：GitHub Actions 构建镜像、服务器只拉取已审核版本；计划提供一键安装和一条命令升级。
- **上游兼容**：定期同步原版 3x-ui 更新，先做安全审计、测试和兼容性评估，再发布专属镜像。


## 第十二阶段：Bot Secret 最小权限与 TLS 域名身份保护（开发预览）

- 后端强制验证 Bot Token Secret 文件为真实、权限受限的普通文件（父目录不可被其他用户写入），读取时核对打开的 inode，拒绝多行或控制字符。即使绕过安装脚本也要执行这些检查。
- HTTPS 证书热加载除了有效性、配对和到期日，还要求**保留旧证书 DNS/IP SAN**，避免签到了其他域名的有效证书却造成面板 HTTPS 故障。
- 核查目标 Fork 22 个现有源文件的关键补丁锚点；添加独立 Go 单测和实际补丁复制契约测试。
- **仍未完成整仓 Go/React/Docker 构建与 Telegram 实机测试，不可安装到生产服务器。**

详见 [第十二阶段修改记录](docs/PHASE12-CHANGELOG.md) 和 [实际测试报告](docs/PHASE12-TEST-REPORT.md)。

## 第十一阶段：完整构建门禁与 Telegram 原始数据外传防护（开发预览）

- 修复 CI 顺序：先执行公开源码和完整 Git 历史隐私检查，再构建 React 管理界面及 Telegram Mini App，确认 `internal/web/dist` 存在后运行完整 Go 测试与构建；最后才构建**不推送**的 Docker 测试镜像，并扫描最终镜像的全部层。
- 在 Vela 模式下禁止原版 Telegram Bot 自动或手动发送整个 SQLite 数据库及生成的 Xray `config.json`，拦截 `/panel/api/backuptotgbot`，隐藏 Bot 菜单中的远程数据库备份按钮；本地备份与恢复仍保留。
- Vela 模式不自动发送原版未经再次授权的周期性详细统计报告；启用过的明确其他 Telegram 通知仍可能将信息发往 Telegram，需由操作者知情配置。
- 证书路径已配置但证书或私钥读取失败时，Vela 不再静默回退 HTTP，而是拒绝启动 HTTPS 监听；无证书配置时允许由受控反向代理接入本机 HTTP。
- 修复针对同一上游源文件重复修改导致新改动丢失的问题。针对性离线测试通过；**真实 GitHub Actions、完整 Go/React/Docker 构建尚未实际跑通**。

详见 [第十一阶段变更记录](docs/PHASE11-CHANGELOG.md) 和 [第十一阶段测试报告](docs/PHASE11-TEST-REPORT.md)。

## 第十阶段：TLS 续签热加载与证书 UI 修复（开发预览）

- 修复提醒已启用但证书页面仍显示「未启用」的问题；统一 API 的 `obj.certificates` / `obj.alertsEnabled` 响应契约。
- 面板直接使用 Go HTTPS 时，Vela 每隔至少 30 秒在下一次握手前尝试载入磁盘中成功续签的证书和私钥；新证书与私钥**必须匹配、当前有效且不可回退到更早到期的版本**。发现半写入、损坏或过期的文件时，继续向新连接提供上一次可用证书。
- 新增实际 TLS 无 SNI 握手测试、并发 Race 测试和跨前后端接口契约测试。
- **不会执行 ACME 签发和续签命令**；原版 ACME / Certbot 负责续签，外部 HTTPS 反向代理（如 Nginx/Caddy）负责自己独立的热加载。
- 本阶段仍为**未整仓构建、未实机验收的开发代码包**，不建议正式生产安装。

[第十阶段变更记录](docs/PHASE10-CHANGELOG.md) · [第十阶段测试报告](docs/PHASE10-TEST-REPORT.md)。

## 第九阶段：证书到期提醒与 Telegram 私聊防护（开发预览）

- 增加证书到期提醒调度，每天按面板时区 **09:00** 检查证书；只有管理员在本地显式设置 `XUI_TG_CERT_ALERT_ENABLED=true` 才会发送，默认**完全关闭**。
- 通知只发送给白名单中的 Telegram **私聊 ID**，不包含域名、IP 地址、Token、证书私钥或文件路径；以本地 `0600` 状态文件为每位管理员和每个预警阶段去重，防止服务重启重复推送。
- Telegram 机器人在 Vela 模式下**只从 Docker Secret 读取 Bot Token**；Secret 丢失立即失败，不再先读取旧数据库 Token。小程序启动按钮仅允许在白名单管理员私聊出现。
- 独立证书页面新增通知状态显示，但仍为**只读**，无法代表独立申请／续签流程已完成。
- 此版本没有完成真实 Telegram/Docker/整仓构建验证，禁止作为生产安装包。

[第九阶段改动和配置说明](docs/PHASE9-CHANGELOG.md) · [项目续接档案](docs/PROJECT-CONTINUITY.md)。

## 第八阶段：防旧签名版本重放和开发连续性（开发预览）

- Vela 发布清单在原有离线 Ed25519 签名和镜像固定摘要之外增加 **`releaseSequence` 单调版本号**；本地维护工具拒绝低于已记录序号的旧签名清单。
- 成功切换版本后安全记录序号；如果新版本升级失败、或恢复到一半断电，恢复旧镜像时也恢复对应的发行序号。
- 新增 [`docs/PROJECT-CONTINUITY.md`](docs/PROJECT-CONTINUITY.md) 开发续接档案，保证聊天窗口变长、未来更换对话时也能按约定接续工程。
- **当前仍未完成真实镜像构建、Telegram 及生产测试，也未发布正式签名公钥，不能用于生产。**

[第八阶段改动](docs/PHASE8-CHANGELOG.md) · [第八阶段验证记录](docs/PHASE8-TEST-REPORT.md) · [项目续接档案](docs/PROJECT-CONTINUITY.md)。

## 第七阶段：可核验的签名发布与更严格的隐私保护（开发预览）

- 增加**可达 Git 历史对象的离线扫描**：即使密钥已从最新源码删除，只要留在历史提交中也会阻断发行。无法验证历史以外的缓存和已删除引用，仍需人工审计。
- 将未来的发布清单校验升级为 **Ed25519 离线数字签名 + 固定公钥 SHA256 指纹 + 镜像 Digest**。公钥尚未正式配置时，更新命令**主动拒绝执行**，不会触及服务器数据。
- Mini App 只从本地 Docker Secret 读取 Bot Token，拒绝环境变量回退、符号链接和过大的文件。
- 证书管理 API 不再返回服务器上的证书或密钥文件绝对路径；前端显示配对状态。
- Docker Host Network 管理端口可显式配置，维护健康检查不执行 `.env` 里的 Shell 内容。
- 升级恢复中再次断电导致部分数据目录缺失时，恢复命令可利用已有安全归档重建目录。
- 补丁对旧文件的保护更严格，部分复制失败会回滚；任何实装必须在独立开发分支完成。

[第七阶段改动](docs/PHASE7-CHANGELOG.md) · [离线发行签名方案](docs/RELEASE-SIGNING.md) · [第七阶段测试报告](docs/PHASE7-TEST-REPORT.md)。**仍未发布正式镜像，不可生产安装。**

## 第六阶段：异常中断恢复与隐私门禁（开发预览）

- 增加持久化 `.pending-update` 升级记录及人工恢复命令 `vela recover`，避免升级中途断电后覆盖旧备份。
- 备份/恢复时校验归档成员，拒绝路径穿越、危险链接或设备文件；若现有证书目录使用目录外软链接，需人工整理后再尝试更新。
- 增加 `deploy/vela/privacy_audit.py`，检查 Git 源文件与潜在 Docker 构建目录中的可疑密钥，并核对 `.dockerignore`，不向任何网络上传私人资料。
- 在 GitHub Actions 的只读 PR 检查中增加隐私门禁。开发版本禁止在生产安装。

详细说明：[第六阶段改动记录](docs/PHASE6-CHANGELOG.md)。**本阶段未发布 Docker 镜像或一键安装脚本；整仓与生产实机验收仍未完成。**

## 第五阶段：升级一致性与隐私保护（开发预览）

本阶段集中修复上一版中真实存在的隐患，**没有发布生产镜像，也没有执行生产安装**：

- **修复备份/切换时序**：`vela update` 从拉取镜像、暂停面板、创建 SQLite/证书/ACME 一致性备份到新版本接管期间，旧服务不会因备份完成而提前重启。否则更新失败后回滚会丢掉快照之后的新写入。
- **更严格的健康检查**：新增 `/tg-miniapp/health`，检查 Mini App 模式已启用、Bot Token 已配置且面板管理员数据库可读取，返回 `204`；更新器必须识别此专属接口，不能将普通 `200` 登录页当成升级成功。此检查**不代表** Xray 全部协议、节点或 Telegram 端内测试通过。
- **Docker 构建隐私**：更新 `.dockerignore`，防止 `.env`、`secrets/`、`acme/`、`backups/`、`failed-updates/` 等真实运行资料被原版 Dockerfile 的 `COPY . .` 带进构建上下文。
- **修复预检查配置错误**：`preflight.sh` 默认与 Compose 一致，读取 `.env` 同级 `secrets/vela_bot_token`，不再要求示例文件中并不存在的 `VELA_BOT_TOKEN_FILE`。
- **本地维护更安全**：防止组/其他用户可写安装目录、符号链接备份目录或维护锁文件，备份生成后检查归档是否可读取。
- **日常操作**：加入只读的 `vela status` 与 `vela logs`，不操作生产状态，不上传日志到 GitHub。
- **离线回归测试**：17 项 Python 模拟测试通过，Go `tgminiapp` 安全测试及 race 检查通过，Bash 语法检查通过。

以上安全改动只在补丁和测试环境中验证过；**CI、Docker、真实 Telegram、证书写入/续签、完整 Xray 回归和一键安装仍为发布阻断项**。发布清单 `stable.json` 尚不存在，`vela update` 不能用于生产。

## 第四阶段：升级与部署安全验证（开发预览）

这次重点建设独立的 Vela 维护工具，**不再改动原版 `docker-compose.yml`**，保持原版升级友好。

- `deploy/vela/compose.host.yml`：独立的 Docker Host Network 候选部署模板，保留 Xray 自定义 TCP/UDP 入站能力；Go Web 管理器在 Vela 模式下强制只绑定 `127.0.0.1`，仍需要可信的 HTTPS 反向代理。
- `deploy/vela/vela`：本地维护命令，提供 `doctor`、`backup`、`update`；更新只接受 `ghcr.io/smgsp6/3x-ui@sha256:<digest>`，不会下载执行原作者的更新脚本。
- `vela update`：准备从本 Fork 的 stable 清单获得已审核镜像；镜像拉取失败不停止原服务，升级前停止写入并备份 SQLite、证书和 ACME，健康检查失败则恢复旧镜像、旧数据，并保留故障数据以供排查。
- `tests/test_maintenance_cli.py`：使用虚拟 Docker 和下载工具模拟更新过程，**不接触真实服务器和网络**。
- `.github/workflows/vela-pr-check.yml`：新增只读的 PR 审查流程模板，运行 Go/React/安全检查；尚未上传仓库，也未实际在 GitHub Actions 运行。
- `apply_to_repo.py`：仍要求唯一仓库 `smgsp6/3x-ui`、独立分支、特定审计提交、干净工作树；增加写入中途失败的文件恢复。

第四阶段基线测试：`GO111MODULE=off go test -race ./internal/web/service/tgminiapp`，以及 Python 自动化共 **11 项**（GitHub 连接器不可写，尚未执行整仓/容器实机测试）。

> **不能直接用于生产安装**：尚未发布 `stable.json`、签名与审计通过的 Vela 镜像、HTTPS 反向代理自动配置或一键安装器。Host Network + NET_ADMIN/NET_RAW 会扩大容器对宿主机网络和防火墙的权限，必须在 VPS 上单独审计与验证。详见 [Vela 更新设计](docs/vela-updates.md)。

## Vela 第三阶段：视觉品牌与升级安全底座

![Vela 品牌](brand/vela-logo-horizontal.png)

本阶段在第二阶段基础上补充了可审查的源代码，而非可安装版本：

- **Vela 正式视觉**：已打包横版 Logo、独立 APP 图标和 16/24/32/64/192/512 PWA 图标；小程序欢迎页和侧边栏接入图标，PWA Manifest 统一显示 Vela。保留旧 PWA 图标路由，减少升级冲突。
- **接入修复**：修正证书 API 控制器缺少的 Go `service` 导入，补充 TypeScript PNG 模块声明。
- **Telegram 安全**：在签名和白名单验证之外拒绝签名数据中明确的群聊启动来源；账号凭据更新后保留已验证的 Telegram Session，未经验证的旧 Session 无法获得 Vela 权限。
- **证书安全**：检查 PEM 文件是否为普通文件，限制最大读取大小，测试异常大文件场景；暂不接受任意上传文件路径。
- **本地隐私**：补充 `.gitignore` 对 `secrets/`、`db/`、`cert/`、`acme/`、`pgdata/` 和密钥文件的排除规则。
- **部署边界**：Vela 将自身 Web 管理服务改为仅监听本机，第四阶段提供独立的 Host Network Compose 模板；原版 Docker Compose 不改动。公开 HTTPS 反向代理与 Xray 入站端口配置仍需实机测试。
- **补丁保护**：严格限定 `smgsp6/3x-ui` 原仓库、已审计的 HEAD `5297fd3c...`、非 `main/master` 分支和干净工作树；上游内容不匹配即拒绝应用。

### 第三阶段代码检查

```bash
# 在本包内（无需联网，不会触碰服务器或其他 GitHub 仓库）
GO111MODULE=off go test -race ./internal/web/service/tgminiapp
python3 -m unittest discover -s tests -v
python3 -m py_compile apply_to_repo.py
sha256sum -c SHA256SUMS
```

### 应用到自己的 Fork（代码审查后，仅用于开发测试）

```bash
git clone https://github.com/smgsp6/3x-ui.git
cd 3x-ui
git switch -c feat/vela-miniapp
python3 /path/to/vela-phase12/apply_to_repo.py . --check
python3 /path/to/vela-phase12/apply_to_repo.py .
```

补丁锁定了上游的一个特定审计基线版本。如果 Fork 已同步到较新提交，脚本会**主动失败**，应重新审核合并点，不能绕过它强行覆盖。

**真实 Docker 镜像构建、Telegram 实机登录、完整 Xray 功能回归、证书写入/续签和一键发布仍未通过验收，不能用于生产安装。**

## 开发阶段状态

| 功能 | 状态 |
| --- | --- |
| Telegram `initData` HMAC-SHA256 验证及管理员白名单 | 初步实现，含单元测试 |
| Telegram Mini App 独立登录入口 | 初步接入，需要整仓构建验证 |
| 原版登录会话隔离、保留节点 API 身份 | 初步接入，需要集成测试 |
| 独立证书列表及有效期检查 | 初步接入，当前为只读状态 |
| 手机底部导航与启动页 | 初步实现，需视觉和端内测试 |
| 证书上传、主动续签 | 待开发；只读状态与可选到期提醒已实现 |
| 全部原版管理功能的移动端重设计 | 待开发 |
| 多服务器一键升级、健康检查、失败恢复 | 有开发预览命令和模拟测试，未完成实机验收 |
| Docker 镜像发布、一键安装/升级脚本 | 待开发 |
| 全套回归测试、外部安全审计 | 待完成 |

## 安全与隐私

**严禁向公开仓库提交** Telegram Bot Token Secret、管理员密钥、节点 API Token、数据库文件、证书私钥、真实服务器信息、运行日志和备份数据。

Mini App 的前端身份信息不可信；只有后端验证成功才可建立管理会话。提供签名过期检查与管理员 ID 白名单。原版受限节点 API Token 保留，防止误伤已有多节点功能。

请注意：原版已有的管理员 API Token 可能仍具有管理权限。**在实现全面的令牌治理和网络隔离前，不可宣称系统只能通过 Telegram 访问。**

Docker 镜像需要固定版本和摘要并接受安全扫描。不得把 Bot Token 烘焙进镜像，也不得将生产 `.env` 提交至 Git。

## Docker 部署（开发阶段）

仓库沿用原版 `Dockerfile` 与 `docker-compose.yml`；第四阶段**不再直接推荐叠加旧版 `deploy/miniapp/compose.override.yml`**，因为原版端口映射与 Vela 模式的本机 Web 绑定不兼容。改用独立的 `deploy/vela/compose.host.yml` 作为待验证的候选。正式一键安装脚本和预构建镜像仍在开发。

1. 备份已有数据库，并在**测试环境**中验证新版本。
2. 在服务器本地创建 `.env`，并在本地创建 `./secrets/vela_bot_token` 私有文件，文件权限均为 `0600`。Bot Token 不放入环境变量或 GitHub。
3. 使用支持 HTTPS 的反向代理或服务器 TLS 配置，将 Mini App 的公开地址指向本服务根路径。
4. 将 HTTPS 地址配置为 Telegram BotFather 的 Mini App URL。

示例命令（**仅供开发测试，不代表已经可用于生产环境**）：

```bash
cp deploy/miniapp/env.example .env
chmod 600 .env
# 编辑 .env 填入自己的私密参数，不要上传到 GitHub
# 仅为说明当前代码结构，不可直接当正式安装命令执行
# 正式发布前需配置并审核独立 Host Network + HTTPS 反向代理方案
```

不要在内存较小的生产 VPS 上直接构建整套 React / Go 项目，等专属 GitHub Actions 镜像发布后再使用拉取式更新。

## 开发与测试

独立安全核心仅依赖 Go 标准库，可单独验证：

```bash
GO111MODULE=off go test -race ./internal/web/service/tgminiapp
python3 -m unittest discover -s tests -v
bash -n deploy/vela/vela
```

整仓还需要使用上游 `go.mod` 指定的 Go 工具链以及 Node.js 版本运行构建、测试和静态扫描。未经整仓测试通过，不应升级正式服务器。

## 开源声明

本项目基于 [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui) 二次开发，保留原版的版权、署名和 **GPL-3.0** 许可要求，详见 [LICENSE](LICENSE)。

仅用于合法、合规的个人学习与服务器管理。

## Vela 品牌与发布策略

正式名称：**Vela**。GitHub 项目保持 **smgsp6/3x-ui** 不变，便于持续同步上游并保留许可。

只有当整仓 Go/Node 构建、Telegram 实机登录、Docker 镜像签名与多节点回归测试全部通过，才发布可安装的 Vela 镜像及一键安装脚本。在此之前，所有文件都是**开发预览**，不得部署到正式服务器。
