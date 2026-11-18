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

## 10. 第十三阶段实际 GitHub 集成（2026-11-15 更新）

本节比前面在 GitHub 上传之前留下的“403 / 未写入”记录更新，**以本节为准**。

- 唯一开发分支仍是 `smgsp6/3x-ui:vela-dev`，`main` 仍为原始基线 `5297fd3c8495d80fab97ae511553fa545c69e913`。
- 第十二阶段源码包已在 GitHub Actions 临时工作树中验证完整性（79 个文件、固定 SHA256），执行原有 `apply_to_repo.py --check` 和正式补丁应用。Vela 真实源码的 92 个变更于提交 `66a527523591a6aad9aa0932c73b1e7ea9fad781` 写入 `vela-dev`，并用 GitHub API 验证 `internal/web/controller/miniapp.go` 存在。
- 原 ZIP 包里的独立工作流 `.github/workflows/vela-pr-check.yml` 因 GitHub Actions token 不具备 workflows 修改权限而单独由已连接的 GitHub 工具提交；完整构建工作流已启用，在 `vela-dev` 上运行。
- 原始上游基线包含 4 个现有源码中 PEM 字符串扫描告警和 24 个历史私钥格式扫描告警。开发 CI 现在使用固定原版 Blob SHA 和基线扫描结果对比，要求**不增加**告警。不能将此视作正式发布所需的零风险历史审计。
- ZIP 中的原始 `apply_to_repo.py` 已补充到仓库根目录，以支持旧开发包的回归测试；CI 对它实施第十二阶段固定 SHA256 校验。
- 已有 GitHub Actions 初步通过了源码隐私基线差异、Git 运行时私密文件检查、前端 TypeScript 类型检查；完整 React 单测、Go 全量测试、Python 离线回归与 Docker 构建要以最新 CI 的实际最终结论为准，不能预先宣称通过。
- 本阶段没有修改线上服务器、发布 Docker 镜像或生成正式一键安装脚本。签名生产发行密钥尚不存在，`vela update` 仍故意禁止生产升级。


## 11. 第十三阶段续开发：整仓编译与浏览器测试（2026-11-15）

- 实际 GitHub Actions 运行 `43686534916` 中，React 1,986/1,986 项断言通过，但浏览器测试因 CI 运行器缺少 Playwright Chromium 返回非零。已在 `.github/workflows/vela-pr-check.yml` 增加锁定依赖环境下的 `npx --no-install playwright install --with-deps chromium`，**仍以新一轮实际浏览器测试最终结论为准**。
- 独立 Go/React 编译冒烟检查使用 `.github/workflows/vela-build-smoke.yml`，仅有 `contents: read`，不会发布镜像或二进制。第一次执行 `43687146886` 发现 `internal/web/service/tgbot/tgbot_router.go` 两处 `homeRows()` 遗漏传 `chatId`，已在提交 `fec05ec856dd0af836cfbcde158c7791d6c01ee0` 中修正。
- 第二次编译运行 `43687514622` 发现上游既有 Go 测试调用 `homeRows()`，而 Vela 新签名要求参数。为避免批量修改上游测试和其他旧调用，提交 `dfd312a57f80d3cf2a9c31bb93f49e856f4f7bc6` 将签名改为兼容的可选 `chatID`：**省略参数时不会展示 Vela WebApp 按钮**，有明确数字用户 ID 时仍需满足 `tgminiapp.AllowedUserID` 校验。
- 一次性写权限源码集成流水线已在提交 `4b8e62b6aa69b980899945885826ce64c32b6c40` 中删除，自动构建工作流保持只读权限。
- 当前重跑检查：Go/React 只读冒烟工作流 `43687931803`；完整安全与构建检查 `43687931783`。截至更新本节时，隐私门禁和 76 项 Python 模拟/离线回归通过，Go 整仓编译与浏览器测试仍在运行。**不应将未完成的 CI 当作通过**。
- 按用户新指示：不做任何额外的语言精简或默认语言改动；原版 14 种语言和上游兼容性必须保留。
- 生产安装、真实 Telegram 登录、多节点、真实 Docker 部署、证书签发与回滚尚未验收，仍禁止正式安装发布。


## 12. 第十三阶段整仓验收进度（2026-11-15）

- GitHub Actions `43687931803`、`43688837769` 的独立只读构建验证通过：Node 26 React 面板与 Telegram Mini App Vite 构建、`go:embed` 入口检查、Go 1.27.4 全包编译、Go 面板可执行文件构建；第二轮额外通过 `TestRouteRegistryContract`（API 文档清单与实际路由必须一致）。
- GitHub Actions `43688727166`：隐私门禁、76 项 Python 离线回归、React 单元/Playwright 浏览器测试、Go 全量测试、Mini App Go Race、Go 可执行文件构建与依赖安全检查全部成功。Docker 作业被安全门禁阻止，原因是该作业使用默认浅克隆，找不到原始 Git 基线；**不是 Docker 镜像验收通过**。
- 新增的 `GET /panel/api/certificates/status` 在 `internal/web/routes_contract_test.go` 检出缺失文档，已补入 `frontend/src/pages/api-docs/endpoints.ts`，只描述授权访问与证书元数据，不输出私钥或本地路径。
- `.github/workflows/vela-pr-check.yml` 中的 Docker checkout 已改为 `fetch-depth: 0`，使原本必须执行的历史隐私基线检查能够工作。重跑 `43689490404` 的实际 Docker 结果尚未确定，不可宣称成功。
- 当前所有改动仅在 `vela-dev`，上游 `main` 和 Go 模块路径未变；原版 14 种语言不再主动调整。
- 依然**没有**真正安装到服务器、测试 Telegram WebView 或发布生产 Docker 镜像/一键安装。生产升级、回滚、ACME 续签、Xray 多节点和镜像层隐私扫描仍需通过后续真实验收。


## 第十三阶段：全链路 CI 和真实 SQLite 容器重建验收（2026-11-15）

- GitHub Actions `43707314982` **4/4 作业全部成功**：固定上游隐私差异扫描、React/Playwright、Go 全量测试与构建、93 项 Python 离线回归（包括备份恢复模拟）、以及 Vela 专用安全 Dockerfile 的无缓存镜像构建与所有层隐私审计。完整镜像：**9 层、2,385 个文件，扫描 PASS**。这是开发镜像验收，不包含生产凭据或任何镜像推送。
- GitHub Actions `43707849395` **成功**：在关闭外部网络、取消额外 Linux capabilities 并设置 `no-new-privileges` 的隔离环境，完成面板启动、TCP 监听、Fail2ban CLI 检查、合成 SQLite 数据库创建、删除测试容器后使用同一个本地受限数据目录重新创建容器，核验数据库仍存在并保持 `0600` 权限，最后再次完成 9 层/2,385 文件隐私扫描 PASS。合成目录所有权采用 `root:root`、权限 `0700`，避免弱化容器运行时权限来通过测试。
- SQLite 首轮重建测试 `43707220860` 失败：宿主机测试目录为普通 Runner 用户所有且 `0700`，在容器已删除额外 DAC capabilities 后无法初始化数据库。诊断 `43707722532` 验证容器退出且未创建数据库；修改测试目录所有权而不开放访问权限后 `43707849395` 通过。此结论只对该隔离路径、单机 SQLite 和正常重建成立，不等于灾难恢复或升级回滚通过。
- `main`、Fork、Go 模块路径、原版 Dockerfile、语言文件及用户线上服务器均未修改。未上传真实 Bot Token、管理员身份、数据库、证书或节点信息。所有镜像仅保留在临时 GitHub Runner，没有正式推送。
- **仍阻断正式安装与发布**：缺真实 Telegram Mini App WebView 签名登录和管理员白名单/会话/CSRF/HTTPS 端到端验收、真实 Xray TCP/UDP 入站和多节点联调、ACME 与到期提醒、实际升级备份恢复和断电中断回滚、签名发行清单与固定供应链 digest。原版构建脚本的可变下载来源和 24 项上游 PEM 历史对象仍需生产发布审计。

结论：Vela 现已通过开发源码整仓 CI、真实 Docker 层审计、隔离容器启动及合成 SQLite 正常重建测试，**但仍是开发预览，禁止直接对用户生产服务器发布一键安装或未经授权部署**。


## 第十三阶段：真实停机 SQLite 快照恢复与重启验收（2026-11-15）

- GitHub Actions [`43709075622`](https://github.com/smgsp6/3x-ui/actions/runs/43709075622) **全部成功**：在无生产 Secret、无外部网络及额外 Linux capabilities 的隔离 CI 中构建完整 Vela 开发镜像、实际启动面板并确认 TCP 监听，使用受限本地 SQLite 目录正常重建容器，随后验证以下**真实数据库恢复**场景：
  1. 停止并删除隔离测试容器，确保真实 SQLite 数据库写入停止；PRAGMA integrity_check 通过。
  2. 在独立的测试专用表中写入固定合成标记，提交并执行 WAL checkpoint。
  3. 用仅含数据库文件的本地 tar.gz 创建停机快照，强制归档权限 0600，审核归档成员为单一普通文件。
  4. 故意把合成标记修改为其他值，再从测试快照恢复，核对 SQLite 数据完整性、原始标记和数据库文件 0600 权限。
  5. 使用恢复数据重新启动真实 Vela Docker 容器，再次确认完整性及标记未丢失。
  6. 严格镜像层隐私审计再次成功：9 层、2,385 个文件，PASS。
- 上述实验使用 CI 自建快照及合成记录，**不是**直接通过未发行的 `vela backup`/`vela recover` 在真实发布镜像上完成的签名升级失败、回滚和断电恢复测试；这些仍是生产发行阻断项。也未验证实际客户数据库、大规模写入、PG 数据库或证书/ACME 全量恢复。
- 本轮 GitHub 源码提交 `958463defa62508e34fbb0d962bd35a54d4b1475` 添加隔离恢复测试。没有发布安装命令、镜像或访问用户线上服务器；`main`、原版 Dockerfile、Go 模块路径和语言文件未修改。


## 第十三阶段：真实 SQLite 参与维护 CLI 的故障回滚测试（2026-11-15）

- 本轮提交 `36f54c1d85598b669609a59c9be964445f3fb583`、`bfdd8285a60c1ca35f4b4df73654931706da2237`：在原有的 Vela 维护 CLI 测试中加入真实 SQLite 数据文件，而不是用文本假数据库验证回滚。合成记录仅在临时目录中生成，不涉及客户、节点、管理员或 Token 信息。
- 测试直接执行 `deploy/vela/vela` 的维护代码，使用系统 tar 与 OpenSSL 的测试临时签名密钥，但模拟 Docker 镜像编排和本地健康检查；三类关键场景：① 已签名的候选升级健康失败，恢复 SQLite 快照、旧 Digest 和发行序号、保留故障候选数据；② 中断升级记录存在时，运行 `vela recover` 恢复真实 SQLite 原始记录、证书/ACME 测试目录以及旧镜像引用；③ tar 归档损坏时，拒绝恢复并保留当前数据库、恢复记录及原镜像状态。
- 新增只读专项 CI `.github/workflows/vela-recovery-contract.yml`，执行完整 Git 历史隐私基线、shell 语法以及维护 CLI 测试。GitHub Actions `43710100702` **成功，40/40 项测试通过**；隐私差异检查为零新增发现（检查器报告的上游历史告警是既有对象，不等于全历史无告警）。
- 正式 `vela update` 仍刻意被未配置的发行公钥指纹禁用；测试中的签名密钥只在 GitHub Runner 临时目录生成，绝不配置为正式密钥。
- **验收边界**：真实 SQLite + 归档 + CLI 已验证，但 Docker Compose 调度仍由测试替身模拟。与此前 `43709075622` 实际容器快照恢复测试相互补充，**不能宣称完成真正的签名 Docker 升级、失败回滚、断电故障恢复与 Telegram/多节点生产验收**。没有发布正式一键安装命令。


## 2026-11-16 · 个人内测优先冲刺（分支 vela-dev）

本节覆盖此前文档中的旧进度结论。请勿把历史阶段报告中的“尚无 GitHub 写入/构建”误认为当前状态。

- 最近完整成功基线：`7e1105b5d09cb78cb5a8e939f68f10ecc4d0d45a`；HTTPS 26 项集成 `43748407608` 成功、整仓隐私/React/Go/Docker `43748407591` 成功。先前独立真实 Docker CLI 恢复 `43745266278`、SQLite 恢复 `43745266362` 均成功。
- 2026-11-16 新发现：在 Mini App 模式启用但原版 Telegram 通知 DB 开关未开启的**新 SQLite 安装**中，原有 `internal/web/web.go` 启动门槛可能阻止 Bot 启动，致 `/start` 没有 WebApp 按钮。提交 `2241ba216346947394158fb937fefaf9c23152d5` 改为在 Mini App 模式中独立启动 Bot（原版模式仍尊重原版开关），新增 Go 判定测试。
- 提交 `6681ee53e99976b1bae4afaabeee442ad7d57566`：Go 回归验证授权私聊展示**且只展示**官方 Telegram WebApp 按钮，群聊、无用户身份、非白名单、关闭 Mini App 均拒绝；独立 Go/React 构建运行 `43750432621` 成功。
- 提交 `b891bd9286a8ad679c1ccaa822ea6c755114d118`：个人内测真实手机/隔离 VPS 验收清单 `docs/VELA-PERSONAL-BETA-ACCEPTANCE.md`。这是手动验收方案，不是安装脚本。
- 提交 `d20e69e94fbc2afd29ceaad7707f7fdfc7d0e72d`：确保修改 Bot 启动或 WebApp 按钮时触发真正的隔离 Docker HTTPS 联调，防止只靠编译证明可用。该次 GitHub Actions `43750834946` 需以最终状态为准。
- 本轮完整整仓 CI `43750432591` 需以最终状态为准；编辑本节时隐私/备份恢复已通过，React+Go 后续仍运行中。
- **距离个人试用的真实阻断**：独立测试 VPS + 单独测试 Bot + 真实 HTTPS 域名的人工授权、Telegram 手机 WebView 实机、真实主机防火墙与外部 Xray 节点、停机恢复验证。无真实生产凭据、节点或主机信息写入 GitHub。未发布正式镜像，签名稳定版更新仍被禁用。
- 永远只在 `smgsp6/3x-ui:vela-dev` 修改；`main`、Go module、上游 14 种语言和原版 Xray 功能不变。真实线上服务器须有操作者明确授权才可触及。

## 2026-11-16 · 内测安全收口：Bot Token / API 认证（本轮后续）

- 最新已核实可见的旧 CI 成功基线为 `d20e69e94fbc2afd29ceaad7707f7fdfc7d0e72d`（HTTPS 26 项：Actions `43750834946`）及 `6681ee53e99976b1bae4afaabeee442ad7d57566`（整仓 CI：Actions `43750432591`）。**不能把它们视为下述最新提交的测试结果。**
- `9d3d47607d72373c5fb0efb259292e8c70a51aa5`：新增 `safeTelegramLogError` / `safeTelegramLogPanic`，在 Vela 模式统一隐藏常见 Telegram API 发送、屏幕、按钮和长轮询初始化错误中可能包含的 Bot Token；关闭 Vela 时继续原版的详细错误信息。Go 合成凭据回归 `vela_bot_logging_test.go`。
- `767046eedfc86638bae7f6d788355ed831f34e5c` / `a996126a92621d6c19f704803649e019e428979e` / `970b3786386898da41e8294edc0407e8e02556a3`：严格隔离 Vela Bot 的出站配置，**忽略旧版 DB 自定义 Bot API URL 和 Telegram 代理**，避免向不受信任的 API 目标发送带 Token 的请求；`NewBot` 自身再次执行此规则，而非只在 `Start` 中筛掉配置；原版模式不变。Vela 仍可使用独立的面板 Xray 出站桥接。
- `4e79231e285fa416a6fc781a4847e3ea01917156` / `1e09c2437df632450ba20f6e8195cbeac65c1de6`：`session.IsTelegramMiniAppLogin` 拒绝 `apiAuthUserKey` 注入的 Scoped API/mTLS 身份，强制通过完整 Cookie、nonce、登录 epoch、进程内撤销登记验证。Go 回归覆盖真实本地 SQLite 签名 Cookie、伪造 Telegram 字段和 API 身份组合。
- `cc755c2139af9149d2ffb088bea50d8ae3a3be44` / `58b24aa195bed6954d8c4d9b8952211d664ed078`：扩展 Vela 错误脱敏到通知、内联查询、屏幕艺术、广播发送失败；广播日志同时保护 chat/message/group ID，原版日志行为不变。
- **验收阻断**：经 GitHub API 确认，最新代码已有提交，但 `vela-dev` Actions 列表仍停留在较早提交。GitHub 连接的可用工具提供读日志、修改源码和重跑旧 Job，但**没有启动最新 SHA workflow_dispatch 的动作**；切勿重跑旧 Job 并假称验证最新代码。需在 GitHub Actions UI 选择 `vela-dev` 手动触发下面工作流，确认所有 Job 绿色后才将本轮标记“CI 通过”：
  - `https://github.com/smgsp6/3x-ui/actions/workflows/vela-build-smoke.yml`
  - `https://github.com/smgsp6/3x-ui/actions/workflows/vela-pr-check.yml`
  - `https://github.com/smgsp6/3x-ui/actions/workflows/vela-miniapp-https-auth.yml`
- **用户个人内测阻断未变**：真实 Telegram Android/iOS WebView、独立测试 VPS Host Network、真实 HTTPS 域名、真实 TCP+UDP 对外网络、隔离数据备份/恢复。生产主机未获授权，禁止连接或执行任何安装；勿记录实际令牌、服务器 IP/域名、SSH 密钥或管理员 ID。


## 2026-11-19 · 第十五阶段 CI 与安全验证

- Bot 接收器排空修复 `1d0610cc2b9f5f95e8970bb8f4b1f92a158f119e`，恢复了自动触发；首轮维护步骤失败，随后被取消。修复工作流 Secrets 断言的提交 `0585e40049779aff25efc2d37782c301c69c6665` 的四个 Job 均成功。证据只对应相应提交。[首轮](https://github.com/smgsp6/3x-ui/actions/runs/44341392244) [复测](https://github.com/smgsp6/3x-ui/actions/runs/44341916477)
- 本轮把 Telegram 登录会话绑定到验证签名时所用的 Secret。恢复工具现在先完整检查和解包快照，再停止容器并切换目录；解包失败、目录缺失或容器未能停止时保留现有数据和恢复记录。
- 正式自动化使用 vela-dev 推送触发的 **Vela integration and privacy gate**。HTTPS/Xray 与 Docker 回滚合并在该门禁的 Docker Job 中。每次核对提交和运行须匹配精确 SHA。
- 第十五阶段仍需独立审核、真实 Telegram 手机与经所有者批准的隔离部署环境。VPS、生产部署与发布不在本阶段自动流程内。使用[个人内测验收清单](../../docs/VELA-PERSONAL-BETA-ACCEPTANCE.md)。

### 第十五阶段 · 第二批回归

- 第一批提交 `0794e4b57f1f6446f54c27a31ba2b6db5e46a1fb` 的隐私、应用构建与测试、维护以及 Docker 四个 Job 全部通过。[第一批 Actions](https://github.com/smgsp6/3x-ui/actions/runs/44348648193)
- 第二批提交 `438e6d94dd0c5f731ee1cebdc6f0a4635d4b2995` 通过隐私、维护及 TypeScript 检查。新增前端用例调用未注册的 `toBeVisible` 导致失败，后续 Go 和 Docker 步骤未运行。下一批将该断言改为现有 Vitest 断言，同时核验反馈的无障碍播报属性。[第二批 Actions](https://github.com/smgsp6/3x-ui/actions/runs/44352292186)
- 新增 Telegram HMAC 兼容性回归，覆盖现代 initData 的 `signature` 字段及仍无该字段的旧格式。策略或 Secret 变更会退役旧会话登记，凭据更新通过数据库版本校验并注销当前浏览器会话。
- Bot 更换连接前等待后台广播、媒体预览及旧接收器退出。延迟的内联能力探测无法为新 Bot 写入旧能力。移动登录请求超时时可从 Bot 重新打开。
- TLS 状态读取和热加载使用有上限的文件读取。证书链更新后，即使叶证书未更换，也可以在新握手中使用更新的链。恢复暂存目录也会核实解析后的链接仍位于各自数据根内。
- 证书 CA 信任、真实 ACME 申请/自动续签、真实手机和真实公网 Xray 数据通道另行验收。测试通过仍需所有者批准才能安排隔离环境验收。

### 第十五阶段 · Bot Secret 轮换回归

- 第三批提交 `b134abb28b22914165c81396dca8ec332f32f499` 通过隐私、维护、TypeScript、React/Storybook 测试及前端构建。Go 编译失败，原因是内联能力缓存遗漏了刷新状态字段。下一批补齐该状态并重跑门禁。[第三批 Actions](https://github.com/smgsp6/3x-ui/actions/runs/44353864037)
- 旧 Bot 一旦发现本地 Secret 删除、轮换或模式改变，同一连接即退役。已排队的更新会在分派前重新核验，API 调用会在发出前及回包时核验。已经发出的外部请求仍可能已在 Telegram 执行。
- 用合成 Secret 和替身传输回归验证轮换后的旧连接不会恢复收发请求。运行中的实例需按操作流程重启 Bot，使其使用新 Secret。仓库验收仍按 `vela-dev` Push 的完整 SHA 定位 CI，真实设备和环境留待所有者批准。

### 第十五阶段 · SQLite 备份与订阅 HTTPS

- 备份先向对应 Compose 项目确认容器状态，区分正常停止、尚未创建、查询故障与重启中。无法确认 SQLite 已停止写入时拒绝备份。
- 账户凭据修改在同一数据库事务中验证当前二次验证设置、更新登录版本并完成旧行为所需的 2FA 重置。无效验证码会回滚凭据修改。
- Vela 面板和订阅服务启动时均验证显式配置的证书及密钥，限制文件大小并检查有效期。订阅服务对无效配置拒绝启动，且对有效证书启用热加载。证书未配置时仍支持由操作者配置的 HTTPS 反向代理。
- 独立审核应覆盖订阅监听配置、实际反代与客户端信任，以及重新创建容器后证书续期和 SQLite 恢复。
