# Vela 第十五阶段 · 独立审核结论（2026-11-19）

**审核范围**：仓库 `smgsp6/3x-ui`、分支 `vela-dev`、HEAD `af00d08d82fefa64f533eecbbda964acfb5c4f4d`。本文件保存在**独立审核分支**，不对已核验的 `vela-dev` 分支作写操作。

## 审核结果

**批准第十五阶段三批修改的开发/自动化测试门禁：APPROVED_FOR_CONTINUED_DEVELOPMENT。**

**不批准正式安装/公开发布/生产部署：RELEASE_BLOCKED_PENDING_FIELD_ACCEPTANCE。**

已确认提交的连续顺序为：
1. `f28fb95c423bdaee7ac5f9755527842cbfe89970`（会话取消、证书链与维护路径），CI https://github.com/smgsp6/3x-ui/actions/runs/44449405969
2. `f4fb8a4a630d3cf4297c76b143218b7bb88caa8c`（恢复归档权限、日志脱敏与证书说明），CI https://github.com/smgsp6/3x-ui/actions/runs/44451516337
3. `af00d08d82fefa64f533eecbbda964acfb5c4f4d`（Telegram 原生返回先处理编辑弹窗），CI https://github.com/smgsp6/3x-ui/actions/runs/44453409660

三次 GitHub Actions 均 completed/success，每次四个 Job 成功。最新 CI 包含 TypeScript、React 浏览器测试、Go 全量测试及针对 Mini App/Session/Bot 的 Race、npm 和 Go 依赖审查、临时 HTTPS 与合成管理员登录/注销测试、旧 Cookie 不能复活测试、回环 Xray TCP/UDP、隔离 Docker 恢复/Compose 回滚和镜像分层隐私检查。**CI 成功不等于真实现场通过。**

## 独立代码复核记录

- `frontend/src/api/http-init.ts`：401 调用全局 AbortController，待决网络及等候 CSRF 的 Promise 结束；Mini App 403 写不自动重发；客户端 Abort 无法撤销已到达服务端的写操作。
- `tests/ci_miniapp_https_auth.py`：合成签名、CSRF、注销后权限拒绝，复用注销前旧 Cookie 应 401，新登录不复活旧 Cookie；隔离容器中 Xray 网络仅限回环。
- `internal/web/service/tgminiapp/tls_reloader.go`：新证书必须通过有效期/附带链检查，热更新对比曾使用的完整链并拒绝部分链缺失；真实 ACME/反向代理入口仍需验证。
- `deploy/vela/vela`：维护操作校验安装路径，归档恢复前拒绝 setuid/setgid/组与其他用户可写条目，安全失败时保留当前数据和恢复记录。
- `internal/web/middleware/security.go`：Mini App CSRF 失败不写入路径/IP，而只记泛化事件。
- `frontend/src/components/miniapp/MiniAppBottomNav.tsx`：原生返回键先关“更多”抽屉或默认 Ant Design 编辑弹窗，再返回首页。组件与 Storybook 浏览器测试覆盖默认弹窗顺序。

## 剩余风险与正式放行阻断

1. **Telegram iOS/Android 真机**：私聊启动、注销/重开、弱网、软键盘、原生返回、编辑弹窗，缺少真实 WebView 证据。
2. **真实环境 HTTPS/ACME**：隔离的获授权环境中核对续签、证书链、反向代理呈现证书、防火墙与外网 Xray；不使用生产环境未经授权测试。
3. **物理断电/磁盘恢复**：已有 Docker/SQLite 模拟回滚，不等于真实断电恢复通过。
4. **非阻断边界待完善**：`MiniAppBottomNav.tsx` 的弹窗取消依赖 `.ant-modal-close` / `.ant-drawer-close`，对于 `closable=false`、自定义弹窗、多个弹层或键盘状态，可能吞掉返回操作；需新增回归测试并明确处理策略。
5. **客户端取消不撤销服务器已接收写请求**：对重要变更应有服务端幂等/事务/授权检测，不能承诺旧请求全无副作用。
6. 已审核的3个 SHA只批准其自动化与已检查修改，不涵盖后续新增提交。

## 授权声明

这只是**独立自动化与代码审核的有条件通过**；不授权合并 `main`、安装脚本实际更新、公开 Release、生产 Bot/服务器/证书修改、收费资源或发布私人数据。没有打开的 GitHub PR，故非 PR Approve Review；本次审核以独立文档形式归档。GitHub Issues 在该仓库被关闭（REST 410），无法登记为 Issue。

复验时使用上文固定的 SHA 与 Actions 记录，不以之后移动的分支名作为相同审查对象。
