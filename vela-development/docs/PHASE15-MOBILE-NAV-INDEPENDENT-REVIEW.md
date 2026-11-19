# Vela 第十五阶段后续修复 · 原生返回与移动端独立审核（2026-11-19）

**审核固定对象**：`smgsp6/3x-ui` / `vela-dev` / `51861ca7d30585118dbbec39f2a4347c3ba537e8`，父提交为 `af00d08d82fefa64f533eecbbda964acfb5c4f4d`。
- [对应提交](https://github.com/smgsp6/3x-ui/commit/51861ca7d30585118dbbec39f2a4347c3ba537e8)
- [本轮 GitHub Actions](https://github.com/smgsp6/3x-ui/actions/runs/44469408704)

## 结论

**APPROVED_FOR_CONTINUED_DEVELOPMENT_AND_FIELD_ACCEPTANCE_PREPARATION**：本次代码可通过**开发/自动化测试门禁**，继续个人内测准备和独立现场验收。

**RELEASE_BLOCKED_PENDING_FIELD_ACCEPTANCE**：**没有批准**正式安装、生产环境修改、签名 Release、合并到 `main`、真实 Telegram Bot/证书/服务器操作或付费资源。

## 独立核验事实

1. GitHub `vela-dev` 的 HEAD 确实为 `51861ca7d30585118dbbec39f2a4347c3ba537e8`，提交父项为上一轮已审核的 `af00d08...`；`main` 仍是独立 SHA `5297fd3c8495d80fab97ae511553fa545c69e913`。
2. [Actions 44469408704](https://github.com/smgsp6/3x-ui/actions/runs/44469408704) 在该 SHA 上 `completed/success`，四个 Job 均成功：Privacy audit、Backup/recovery、React build/Go tests、Docker image (no push)。包括新增 Chromium 移动端布局脚本。
3. `frontend/src/components/miniapp/MiniAppBottomNav.tsx`：原生返回优先处理可见键盘焦点，再处理“关闭并放弃修改”确认层，随后处理按 zIndex 判定的最高层 dialog、更多抽屉或主页；不可关闭弹窗不触发页面跳转；已给客户端/入站/节点编辑窗添加 `vela-confirm-editor-close` 标记及放弃确认。测试覆盖键盘、锁定层、保留草稿、确认关闭。
4. `frontend/src/components/miniapp/MiniAppBottomNav.css`：支持粗指针横屏的较矮底栏、env 安全区左右/底部 padding、键盘时隐藏底栏；`internal/web/controller/dist.go` 对已登录 Telegram 小程序页加 `viewport-fit=cover`，孤立 HTTPS 集成有对应断言。
5. `frontend/scripts/test-vela-mobile-layout.mjs` **真实运行的检测范围**是 iPhone 14、iPhone 15、Pixel 7 的竖/横屏六组**Chromium 静态模拟 DOM**；断言底栏存在/尺寸、44 CSS px 触控目标、无页面横向溢出及键盘标记隐藏。该脚本**没有验证完整运行应用**、Telegram 原生 top/close/menu 实际位置、iOS 键盘与 content-safe-area、客户端/入站/节点真实页面滚动及最终保存按钮是否遮挡。
6. `docs/VELA-PERSONAL-BETA-ACCEPTANCE.md` 明确列出真实设备、测试专用 Bot/域名、隔离 HTTPS/ACME、防火墙、外网 Xray、备份/恢复与安全失败处理；仍是验收清单而非执行凭证。
7. 已阅读新增代码及相关测试，**未发现本次自动化门禁必须立即阻止继续开发的已证实漏洞**；这不等于全库功能或生产条件通过。

## 剩余事项与改进建议

- **现场 P0**：在用户许可的隔离环境中分别验证 iOS/Android 原生 Telegram WebView：私聊启动、授权/拒绝、键盘出现/收起、编辑草稿保留与放弃、多层不可关闭弹窗、切后台/弱网、注销和恢复，使用合成数据。记录设备/系统/Telegram版本，截图严格脱敏。
- **现场 P0**：独立测试域名的真实 ACME/完整证书链及反向代理出示链、主机防火墙、外网 Xray TCP/UDP、SQLite 与物理断电恢复；这些**未由 CI 证明**，也未得到生产部署授权。
- **非阻断改善**：将移动端测试扩展至真实已登录页面与设备安全区/顶部原生控件模拟，覆盖 iPhone14/15 的更多尺寸、内容和表单按钮碰撞；尽量直接检查 Telegram `contentSafeAreaInset` 或清楚标出 CSS env 与宿主安全区的差别。
- **非阻断改善**：在 `pathname === '/'` 的大范围 DOM `MutationObserver` 路径评估频繁动态页面下的回调/请求帧开销。多层 dialog zIndex 相同/自定义关闭控件场景仍需增强实际交互回归。
- **一致性风险提示**：客户端请求取消无法撤销服务端已经提交的操作，后端幂等、权限和数据库事务仍然是最终保证。
- **保留要求**：Vela 与 `wizard-towers-miniapp` 完全隔离、继续用免费云端和原有四 Job CI；禁止上传真实 Token、密钥、私人数据及未授权服务器配置。

## 审核记录方式

原仓库 GitHub Issues 被禁用，因此独立审核记录保存在单独分支，避免改变已审核的 `vela-dev` SHA。本次未创建 PR、未点击 GitHub PR Approve Review；这是 ChatGPT 的有条件**代码/CI 独立审核结论**。用户进一步明确批准隔离环境后再执行真实操作。
