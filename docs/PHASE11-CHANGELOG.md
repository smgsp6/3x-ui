# 第十一阶段：整仓构建顺序与 TLS 失败保护

## 实际修复

1. 原版 `internal/web/web.go` 使用 `//go:embed all:dist`，但 `internal/web/dist` 未存入 Fork 的主分支。上一版 PR 流水线先运行 `go test ./...`，即使 Go 源码没问题也可能在干净工作树失败。**已调整 CI：隐私审计通过后安装 Go 1.27.4 与 Node 26、执行完整 React 类型检查、单测及 Vite 构建，再执行 Go 全量测试与二进制构建。**
2. 增加 `internal/web/dist/index.html`、`miniapp.html` 和 `login.html` 输出断言，避免忘记包含 Telegram Mini App 或登录入口却通过 CI。
3. 添加单独 Docker 构建门禁：只有隐私、完整代码构建和维护测试全部通过，才在干净的 GitHub runner 上执行 `docker build`；**不会推送镜像**，没有任何生产密钥。
4. 原版配置证书却无法加载时会回退 HTTP；Vela 增加禁止静默降级的分支，关闭监听并返回错误。若没有配置面板证书，仍可在 127.0.0.1 上使用 HTTP，由外部 HTTPS 反向代理终止 TLS。
5. 发现原版 Bot 的三个隐私外传入口：后台定时发送数据库／Xray 配置、管理员手动按键发送文件，以及 `/panel/api/backuptotgbot`。**Vela 模式全部禁止上传原始备份至 Telegram**，保留本地 `vela backup`，同时停用旧版未经单独授权的周期性详细统计报告。维护菜单在 Vela 模式不展示「发送数据库备份」按钮。
6. 增加双重阻止：顶层 API/按钮/自动任务提前退出，底层 `sendBackupFile` 也拒绝文件上传，减少以后合并上游时漏掉一个入口的风险。*其他本来就属于 Bot 的交互式消息、由管理员开启的通知依然会通过 Telegram 网络发送；本条只保证代码中已识别的原始数据库/Xray 配置外传被禁用，不能代表所有网络出口已完成审计。*
7. 修复补丁工具一个合并问题：同一路径若独立调用两次 `modify()`，后者会覆盖前者；现已合并，并新增禁止重复修改路径的回归检查。
8. 新增 `deploy/vela/image_layer_audit.py`，在 CI **不上传镜像 TAR** 的前提下读取 `docker image save` 流，逐层扫描私密文件名、私钥头和高置信度 Token。即使旧层文件后来被删除，也能发现；只输出风险类别与数量，不输出内容或文件名。新增 6 项模拟 TAR 测试。
9. 新增 CI 构建顺序、隐私门禁、发布权限及 HTTPS 退化策略的离线契约测试。

## 当前约束

- 本地环境没有 Docker、Go 1.27.4 或 Node 26，**尚未运行 GitHub CI 的整仓构建或真实 Docker 构建**。
- 新的 CI 由 GitHub 执行后才可据实际日志判断是否完整通过。`smgsp6/3x-ui` 目前仍未获得可用的 GitHub 写入授权。
- Vela 的 `vela update` 仍需要正式签名公钥、构建产物和真实恢复演练，不得在生产调用。
