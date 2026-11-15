# Vela 发布前强制验收清单

开发包仅面向 `smgsp6/3x-ui` 的审核分支。**本阶段尚未达到生产发布条件。**

## 已完成的离线验证

- Go 标准库安全核心：`GO111MODULE=off go test -race ./internal/web/service/tgminiapp`，测试通过。
- 补丁工具：原仓库 HEAD、Origin、分支和干净工作树检查；模拟应用与异常文件复制恢复，通过。
- 运维命令：Bash 语法、镜像摘要限制、敏感文件权限、发布清单拒绝、备份成功、拉取失败、更新后健康检查失败恢复旧数据、备份后不重启旧服务、防止目录符号链接、定制路径与 Vela 专属 204 健康检查，通过（**模拟 Docker / CURL，不是真实运行环境**）。
- 第五阶段 Python 模拟测试 17 项通过，Go 独立验证和 race 检查通过；新增 `.dockerignore` 防止 Docker 构建上下文包含本地私密资料。
- GitHub Actions YAML 静态解析通过，CI 工作流尚未在 GitHub 实际运行。

## 第六阶段额外安全门槛

- [ ] 在真实测试 VPS 上强制断电/重启演练：升级准备、备份完成、候选版本启动、恢复中断各个阶段。
- [ ] Git 工作树、历史提交、Docker 实际构建上下文和最终镜像层不含真实私密数据；对每个候选镜像执行独立密钥扫描。
- [ ] 检验 `vela recover` 对实际 SQLite WAL、TLS/ACME 文件权限和真实 Docker 容器状态的恢复，不仅依赖模拟命令。
- [ ] 明确 Host Network / NET_ADMIN 的宿主机防火墙风险与最小权限防护方案。

## 仍需完成（阻止正式安装）

1. **GitHub 写入授权**：把改动放进 `smgsp6/3x-ui` 的独立开发分支并创建 PR，不改其他仓库，也不直接覆盖 main。
2. **全项目构建**：Go 1.27.4 / Node.js 26、前端 typecheck/test/build、Go go test 与 govulncheck。
3. **安全审计**：代码审查、公开依赖扫描、上游 `DockerInit.sh` 下载的 Xray/MTProto/规则文件的校验与版本固定；审计前禁止发布镜像。
4. **Telegram 实机**：在 Telegram 内部 Mini App 验证服务端签名、管理员白名单、会话过期、非管理员拒绝、群聊拒绝、CSRF/CSP、BotFather HTTPS 入口。
5. **Docker 实机**：在测试 VPS 上使用独立 Host Network 候选 Compose，检验 Web 仅监听 127.0.0.1，TCP/UDP/Xray 入站、Fail2ban 权限及防火墙影响；评估 NET_ADMIN 最小权限方案。
6. **证书管理**：完整实现独立页面内编辑/验证证书配置、续签、到期 Telegram 告警和证书更新回滚；当前只读状态未满足全部需求。
7. **节点兼容**：多节点管理、订阅、Xray 协议、客户端增删改、路由与出站、API Token 范围、安全更新，真实环境回归。
8. **发布链路**：设置分支保护、受保护环境审批、签名镜像与不可变 Digest、签名发布清单；在自己的 Fork 发布正式 stable.json 和镜像。
9. **一次安装**：正式 install.sh 需完成 Docker 安装安全验证、离线/最小权限、HTTPS 反向代理、随机私密凭据生成、可重复运行/回滚、用户数据永不上传、完整安装与升级测试。

## 本地环境限制

本次执行环境：Go 1.23.2、Node.js 22、未安装 Docker、容器对 github.com 无 DNS。不能替代官方构建测试。GitHub 连接器读取成功，但创建分支/提交此前返回 403，因此未推送任何仓库。

上游仓库名和 Go 模块路径均保持不变；请勿将模拟测试视为生产部署许可。

## 第七阶段新增的阻断项

- [ ] 维护者在离线设备生成并安全保管正式 Ed25519 私钥、独立审核公钥，发布通过审查的 CLI，并把正式公钥指纹写死进代码；**当前为禁用占位值**。
- [ ] 正式 `stable.json` 和 `.sig` 共同发布，验证公钥被替换、签名缺失、签名被改、旧签名重放以及密钥轮换行为。
- [ ] 完整审计 Docker Host Network + NET_ADMIN/NET_RAW、入站端口、Xray 进程、Telegram WebView 的完整登录与 API 鉴权。
- [ ] 在测试 VPS 演练升级备份/中断/二次中断/回滚、SQLite WAL 和外部数据库迁移。
- [ ] 发布前检查 `frontend` 不展示真实主机证书或密钥路径，Docker 容器绝不通过环境变量接受 Bot Token。

- [ ] 完整克隆并执行 `python3 deploy/vela/git_history_audit.py .`，针对历史中任何误提交进行人工核实并立即轮换泄露凭据；`git push` 公开后，简单删除当前文件不能撤销泄露。

## 第八阶段新增必须通过的检查

- [ ] 发布清单的 `releaseSequence` 按稳定版发行次序严格递增，发行后不能重复使用旧序号指向不同镜像；旧签名清单重放必须被本地拒绝。
- [ ] 一键安装器创建 `release.sequence` 的可信基准，并限制权限；缺失或损坏时禁止 `vela update` 自动推断版本。
- [ ] 真正生产环境模拟在版本序号写入前后的断电以及回滚，确认旧镜像与对应发行序号一致。
- [ ] 按最新阶段文档 `docs/PROJECT-CONTINUITY.md` 维护交付物，不能将真实 Token、节点或私钥写入对话续接包。

## 第十阶段新增发布门槛

- [ ] 真实 Go HTTPS 服务器启动、无 SNI 与 SNI 的 TLS 握手、真实 ACME 续签后的证书切换在测试 VPS 通过（本地独立 Go 模块握手测试不能代替生产环境）。
- [ ] 新证书只有在证书/私钥匹配、有效期合法、不倒退、文件不超过安全上限时加载；ACME 半写入／错配需要保留旧证书，并产生安全的泛化告警。
- [ ] 外部 HTTPS 反向代理需要在其自身配置下完成证书续签热加载；Go 热加载只解决 Vela 直接 HTTPS 监听。
- [ ] GitHub Actions `test_certificate_contract.py`、全量 frontend typecheck / build、`go test ./...` 全部通过后才能发布。

## 第十一阶段补充：原始数据和镜像层

- Vela 模式下禁止 Telegram Bot 通过定时任务、维护按钮、API 或底层 `sendBackupFile` 发送数据库、生成的 Xray 配置；必要时使用 `vela backup` 在服务器本地备份。
- 先完成全历史/构建上下文隐私审计，再执行 React/Go/Docker 构建；Go `go:embed all:dist` 要求 React 必须先构建。
- 发布前运行 `docker image save <candidate> | python3 deploy/vela/image_layer_audit.py --stdin`，扫描最终镜像全部层（包括后来删除的敏感文件）；不得在公共 Actions 日志打印匹配内容、不得上传镜像 TAR。
- 镜像扫描之外，必须另行检查 builder 缓存、基础镜像、真实配置、Telegram 与网络出口及构建日志。
- 禁止从 TLS 证书加载失败静默降级为 HTTP；在明确配置了面板 TLS 时 Vela 应拒绝启动。
- 上述 CI 工作流**尚未在真实 GitHub PR 上通过**，不得标为正式可安装。
