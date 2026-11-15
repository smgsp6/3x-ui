# Vela · 多服务器 Docker 安全发布设计（开发阶段）

当前**不是可安装的正式版本**：尚无经过整仓构建、审计和生产环境测试的 Vela 镜像，也没有可用的一键安装命令。**不要将上游 3x-ui 镜像当成 Vela 镜像。**

## 已有基础

- 项目仍然只在 `smgsp6/3x-ui` 开发，不新增其他 GitHub 项目。
- 采用原版 Go 后端、Xray-core、SQLite、React，Vela 是正式 APP 品牌。
- Telegram Mini App 不使用 HTML Widgets；仍使用 Telegram 的标准 WebView、HTML/CSS/JS。
- 由中央管理实例（Master）启动唯一的 Telegram Bot。**不要用同一个 Bot Token 在所有 VPS 上同时运行 long polling**；其它服务器通过受限节点 API/mTLS 纳入管理。
- Mini App 管理会话与受限 NodeSync Token 分开。旧版 Admin Bearer Token 与原版在线自更新必须在专属模式下被禁用或替换。

## 正式安装器验收标准

发布后的唯一入口预计为：

```text
# 尚未发布。发布后将在这里填写指向 smgsp6/3x-ui 已审核版本的固定安装命令。
```

发布前必须满足以下要求：

1. **镜像来源**：只通过 `smgsp6/3x-ui` 的 GitHub Actions 构建；预期以 `ghcr.io/smgsp6/3x-ui@sha256:<digest>` 指定不可变镜像。镜像摘要和供应链验签不能只依赖 `latest`。
2. **一键安装**：引导设置公开 HTTPS 域名、BotFather Token、Telegram 数字用户 ID；任何敏感值只写入 VPS 上 `0600` 配置，绝不写进 GitHub、Dockerfile 或 Actions 日志。
3. **Docker**：预构建镜像在 VPS 拉取，单个 Go+Xray 实例，默认 SQLite；业务数据、ACME 续签状态、证书与私钥持久化。Docker 权限按实际协议和 IP 限制要求分配，不启用 `privileged`、不挂载 Docker Socket。
4. **HTTPS 方案**：为 Mini App 提供合法域名和可校验的证书；与 Xray 443 入站、80 ACME 验证及动态 UDP 端口协调。不能为方便而公开未受保护的 Go 面板端口。
5. **更新**：`vela update` 先拉取并校验带摘要的候选镜像，再停机制作一致性备份；旧服务保持停止直到镜像切换，检查失败恢复旧镜像与原数据。带数据库迁移的版本必须验证可回退数据，不保证通过旧镜像直接降级。
6. **多节点**：`vela fleet update` 首先完成灰度节点测试，再分批更新；禁止把所有生产服务器同时升级。
7. **上游**：只经审核合并 `MHSanaei/3x-ui` 变更、构建本项目镜像。严禁触发原版 `update.sh` 覆盖 Vela。
8. **安全门禁**：Go race、静态扫描、依赖漏洞扫描、React 构建及单测、端到端 Telegram 授权测试、Docker 扫描、签名验证、真实节点协议连接、恢复演练均通过。

## 开发检测脚本

本包提供两个只读开发辅助脚本：

```bash
bash deploy/vela/preflight.sh .env
bash deploy/vela/security-check.sh /path/to/smgsp6-3x-ui
```

它们不会安装、修改或重启服务器；不能代替正式安装器。`preflight.sh` 需要已安装 Docker、Compose 且有正确权限的真实本地 `.env`，**不能在公开仓库内保存真实配置**。

## 端内 APP 体验

- Vela 品牌、APP 启动页、中文优先、浅深主题。
- 固定底部导航：「首页 / 服务器 / 客户端 / 证书 / 我的」。
- 完整保留原版入站、出站、路由、DNS、REALITY、多节点、订阅、日志、备份等业务功能。
- 独立证书页面：证书的域名、有效期、签发机构、匹配结果；后续开发安全配置、续签及 Telegram 告警。

## 当前风险

原版的多种系统级操作、第三方二进制和安装更新机制尚未完成重新验证。开发包的 `Go` 纯标准库单元测试通过，不代表可以部署。**本包仅供代码审查和集成测试。**

## 第三阶段安装流程安全约束

- 不在公开源代码库中提交 `.env`、`secrets/`、`db/`、`acme/`、`cert/` 或其他实际私有数据。
- 补丁只能应用在 `smgsp6/3x-ui` **非默认分支**，且 HEAD 必须与审计的 upstream SHA `5297fd3c...` 相符；任何偏差都停止，人工检查升级冲突。
- 确定 Vela 专属 GHCR 镜像和 digest、验签与公开 release 稳定通道之前，不发布可以直接执行的安装命令。
- 数据库备份应在**停止写入或 SQLite Online Backup API** 下取得一致性快照；复制 SQLite 主库文件同时丢弃 WAL 文件不构成可靠备份。
- 自动回滚只能恢复兼容的镜像、数据库与配置快照；如果数据库发生破坏性迁移，不得直接用旧镜像启动。

### Docker 暴露面

Vela 第四、五阶段**不修改原版 `docker-compose.yml`**。独立候选部署文件 `deploy/vela/compose.host.yml` 使用 Host Network，并在 Vela 模式下让 Go 面板仅监听本机 127.0.0.1。该方案仍需 HTTPS 反向代理与 Xray TCP/UDP 动态端口协调，还必须针对 Fail2ban 的 NET_ADMIN 权限、节点访问和端口冲突进行实机审计。**未完成网络联调之前不要在生产部署。**
