# Vela 第五阶段变更记录

**目标仓库：** `smgsp6/3x-ui`，不重命名仓库，不改 Go 模块，不修改原版 `docker-compose.yml`。本包是 **开发测试补丁，不是生产安装包**。

## 修复了哪些真实问题

1. **严重：更新后回滚丢失数据的时间窗。** 原先 `backup_locked` 在升级前备份完会重新启动旧服务；如果升级失败，备份后产生的新写入会在回滚时消失。现在 `vela update` 用 `backup_locked "$old" true`，把旧服务保持在停止状态直到新版本接管。独立 `vela backup` 仍会备份完自动恢复旧服务。
2. **升级误判。** 原先检查网页状态码 `200/302/307`，可能把旧版登录页当作升级成功。新增 `/tg-miniapp/health`，只允许 Vela 模式启用、Bot Token 已配置、面板数据库管理员能读取时返回 `204`；CLI 只接受 `204`。此接口不验证全部协议和节点。
3. **严重：Docker 构建上下文隐私泄漏。** 原版 `Dockerfile` 中 `COPY . .` 可能打包构建目录中的本地 `.env`、`secrets`、备份和 ACME 资料。Vela 补丁更新 `.dockerignore`，在构建上下文阶段排除它们。
4. **预检与部署模板配置不一致。** 预检查不再强制要求示例 `.env` 里没有的 `VELA_BOT_TOKEN_FILE`，默认从该文件同目录读取 `secrets/vela_bot_token`，和 `compose.host.yml` 保持一致。
5. **本地路径风险。** 禁止对其他用户可写的 Vela 安装目录操作；拒绝符号链接维护锁、备份目录和故障数据目录，减少以 root 运行时的路径劫持。
6. **本机维护便利性。** 增加 `vela status`（基础状态）和 `vela logs`（本地最近日志）命令。日志可能含敏感信息，不会自动上传。

## 验证结果

- 17 项 Python 单元/模拟集成测试：通过，包括候选镜像失败后回滚、备份失败自动启动旧服务、备份后禁止旧服务新写入、私密目录防护。
- `GO111MODULE=off go test -race ./internal/web/service/tgminiapp`：通过。
- 3 个 Bash 脚本语法检查：通过。
- 补丁工具模拟审计基线应用/失败恢复：通过。
- 尚未完成：Go 1.27.4 整仓编译、Node 26 前端构建、真实 Docker 和 Telegram 测试、正式镜像签名和一键安装。

## 未完成的风险（正式发布阻断）

- GitHub 连接器对本 Fork 的创建分支/写入请求返回 403。变更尚未推送。
- `deploy/vela/compose.host.yml` 使用 Host Network 和 Fail2ban 的 `NET_ADMIN` / `NET_RAW`，必须在测试 VPS 上确认防火墙行为和端口冲突。
- `stable.json` 尚未发布，也没有镜像签名或可信发布链路。`vela update` 不能安全用于生产。
- 证书页面目前只读，自动续签、证书上传和 Telegram 到期提醒尚未达到验收标准。
- 多节点、订阅、Xray 动态入站和 API 权限仍需实机端到端回归。

**原则：** 开发中只新增独立模块，修改既有源码时必须锁定基线并通过人工合并审查。不要未经测试直接运行本包里的 CLI 或 Compose。
