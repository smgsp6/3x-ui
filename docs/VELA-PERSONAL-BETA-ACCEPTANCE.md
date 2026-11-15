# Vela 个人内测验收清单（仅隔离测试服务器）

> 状态：候选验收方案，不是安装教程或生产发布许可。只适用于经操作者明确批准的**独立测试 VPS**。禁止接入原有生产 3x-ui 数据库、Telegram 凭据和真实节点配置。

## 0. 先决条件

- [ ] 独立、可重建测试 VPS；与生产服务器、SSH 密钥、Docker daemon、数据盘和防火墙配置完全隔离
- [ ] 测试用途的正式 HTTPS 域名；证书与代理配置已由操作者核实，不使用内网 IP、占位 URL 或关闭证书验证的浏览器设置
- [ ] 专门用于内测的 Telegram Bot；私聊中的被授权管理员数字用户 ID；两者**绝不提交 GitHub、不发送到聊天或公开 CI 日志**
- [ ] 仅测试数据与固定的镜像 SHA256 digest；本地 Secret 文件权限 `0600`、容器数据目录 `0700`
- [ ] 宿主机防火墙和 Host Network 暴露面经过人工检查；现有 `NET_ADMIN/NET_RAW` 仅可在独立 VPS 上评估，不能视为最低权限结论
- [ ] 正式签名发布渠道仍被禁用；当前仅开发分支 `vela-dev`，不使用 `main` 也不提供生产安装命令

## 1. 自动化门禁：先检查，再碰测试 VPS

- [ ] GitHub Actions 最新 **Vela integration and privacy gate** 全部通过（Go、React、隐私、开发 Docker 无推送构建）
- [ ] 最新 **Telegram Mini App HTTPS authentication smoke** 通过（合成 HMAC、TLS、CSRF、Cookie、注销回放拒绝、TCP+UDP 数据通道、SDK CSP）
- [ ] **Vela real Docker CLI recover smoke** 与 **real SQLite recovery lifecycle contract** 通过
- [ ] 仅在测试主机执行审阅过的 **只读** `beta_preflight.py` 和 `vela doctor`；两者的通过结果不代表允许安装
- [ ] 本地确认 GitHub 开发镜像尚未正式签名发布，禁止把 CI 临时 `vela-ci-*` 标签冒充生产 Digest

## 2. Telegram 手机真实验收（必须真人参与）

- [ ] 在 Android Telegram 和/或 iOS Telegram 中与测试 Bot **私聊**，发送 `/start` 后能看到「🚀 打开 Vela」
- [ ] 点击按钮，使用官方 WebApp 打开，而非普通外部浏览器或 Telegram HTML Widget
- [ ] 合法管理员可以建立会话；不存在权限的账号、群聊按钮或过期会话均不能进入管理面板
- [ ] 登录后依次访问首页、服务器、客户端、证书和「更多」里的原版 Xray 功能
- [ ] Telegram 原生返回按钮先关闭抽屉，再回首页；在首次打开小程序时不会跳出 Telegram
- [ ] 注销后立即无法访问管理 API；返回/重放旧 Cookie 不应恢复权限；再次进 Bot 重新登录才可访问
- [ ] 记录测试结论仅包含 `PASS/FAIL` 和不含私密信息的错误分类。**不记录 initData、Token、Cookie、证书、域名、管理员 ID 或含隐私的截图**

## 3. 独立 VPS 与 Xray 验收

- [ ] HTTPS 真实证书链、反向代理头部、CSRF 和 WebSocket 均符合配置；HTTP 不允许绕过认证
- [ ] Host Network 的管理端口只监听预期地址；人工确认 VPS 公网入站和 Xray TCP/UDP 规则，没有意外的公开后台或无认证代理
- [ ] 合成测试客户端经实际外部网络通过 Xray 通信（TCP 和 UDP），统计和订阅信息正确；测试后移除客户端与临时入站
- [ ] SQLite 数据写入后，真实 Docker 服务重启仍可正常读取
- [ ] 使用测试数据执行停机备份、恢复、候选镜像失败回滚，复核 SQLite 完整性、证书/ACME 本地状态以及文件权限
- [ ] 断电/中断恢复流程经测试机独立演练；恢复记录损坏时保持数据不被破坏

## 4. 放行判定与失败处理

- **只有第 0–3 节全部通过，才能考虑向单一操作者开放限量个人内测**。个人内测不是稳定版；不承诺零停机或自动升级。
- 任一失败：停止试用，不在生产主机尝试重现；仅记录不含隐私的失败阶段，在 `vela-dev` 修复并重新测试。
- 正式发布仍需要 ACME 真实签发/续签、受保护的发行密钥、签名清单、镜像来源验证、完整安全审计以及正式安装/升级验收。

## 给操作者的最小确认事项

只需私下确认**是否已经拥有独立测试 VPS、测试 HTTPS 域名、单独测试 Telegram Bot，以及准备用 Android 或 iPhone 验证**。不需要在聊天中提供 Bot Token、SSH 凭据、证书私钥或现有服务器地址。

此清单不执行任何安装、访问服务器或 Telegram API 操作。
