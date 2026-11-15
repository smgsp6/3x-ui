# Vela · Telegram Mini App 开发版接入说明

## 现有成果

- 使用官方 HMAC-SHA256 验证 Telegram Mini App `initData`，验证 `auth_date`，限制最大 5 分钟，要求单个数字用户 ID 属于白名单。
- 原版 Go 会话增加 Mini App 身份标记；开启专属模式后旧浏览器账号密码不能建立被接受的会话，原版受限 node-sync API Token 保持兼容。
- Mini App 入口和 React 启动页，官方 SDK 来自 `telegram.org/js/telegram-web-app.js`，不使用 Telegram HTML Widgets。
- 新增证书只读 API 和独立证书管理页面，展示面板与订阅证书状态，拒绝客户指定任意证书文件路径。
- Telegram 模式下设置 Secure Cookie，并对会话寿命设上限。
- 底部 APP 导航在 Mini App 模式中显示，其他页面继续沿用原版业务 API。

## 环境变量（仅服务器本地）

- `XUI_TG_MINIAPP_ENABLED=true`：启用专属模式，默认关闭。
- `XUI_TG_MINIAPP_ADMIN_IDS=123456789`：管理员 Telegram **数字**用户 ID，多个用逗号分隔。缺失或值无效时拒绝登录。
- `XUI_TG_MINIAPP_BOT_TOKEN_FILE=/run/secrets/vela_bot_token`：指向仅存放于服务器上的 Bot Token Secret 文件；不能提交到仓库。绝不能提交到仓库。

测试 Docker Compose 覆盖配置：`deploy/miniapp/compose.override.yml`。Docker 容器里的进程必须实际读到上述环境变量才能启用模式。Mini App 的 URL 必须使用 HTTPS。

## 当前限制（必须先补齐再生产部署）

1. 当前只实现 Telegram 签名登录和证书只读页；**证书续签、上传、自动到期提醒、全部页面的 APP 化、一键安装和舰队升级尚未完成**。
2. 需要在用户实际 Fork 的整仓中运行 Go 1.27.4、Node 26、npm 11 的全部构建、测试、静态扫描和 GitHub Actions。
3. API Token 的历史管理权限需逐一审查，Mini App 模式不应仅依赖前端隐藏 URL。
4. Mini App 登录 Cookie 在 HTTPS 反向代理下使用 `Secure`，纯 HTTP 本地开发需另行配置测试入口。
5. 用户要求持续同步上游源码，但绝不直接运行原版指向 `MHSanaei/3x-ui` 的在线更新脚本覆盖此 Fork。
6. 原始项目的 GPL-3.0 许可与署名必须保留。
7. 官方 Telegram JS 依赖需在最终发布时进一步审计加载策略和 CSP；目前仅在启动页开放 SDK 的 CSP 域名。

## 安全验证

```bash
GO111MODULE=off go test -v ./internal/web/service/tgminiapp
```

该命令只验证安全核心和证书扫描的单元测试，不代表系统通过完整安全审计。

在你的 `smgsp6/3x-ui` Git 工作树中运行 `python3 apply_to_repo.py /path/to/cloned/fork --check` 可以验证源代码匹配；随后去掉 `--check` 执行。脚本**拒绝操作其他仓库**，并要求目标工作树无未提交更改，避免覆盖你的其他修改。

## 第二阶段增量

- 原版 Telegram Bot 自动读取仅在服务器端保存的 Mini App 环境变量，支持私聊首页的「🚀 打开 Vela」官方 WebApp 按钮。
- 禁用旧版无限制 Admin Bearer API Token 作为替代登录渠道；受限监控与节点同步 Token 仍可使用。
- 禁止 Telegram 专属模式下任何原版管理路径或 NodeAdmin Token 调用原版远程自更新脚本。
- 配置 URL 要求 HTTPS，不接受凭据、查询参数和片段；非法配置默认不展示启动按钮。
- 禁止通过证书状态接口返回私钥文件位置；增加尚未生效的证书测试。
- 新增 Docker/隐私发布前检测脚本。

**未完成：** 原版 Bot 其他功能权限回归、安全扫描、HTTPS 代理和证书一键配置、实际 Docker 预构建镜像、真正的一键安装，均不能用于生产环境。

## 第三阶段：Vela 正式视觉与安全校验

- 已将确定的 Vela 航海科技 Logo 做成品牌图和 16/24/32/64/192/512 尺寸的 PWA 图标，保留原版资源供兼容使用。
- 小程序启动页、侧边栏和 PWA Manifest 更新为 Vela 品牌。
- 证书读取前检查目标是否为普通文件及大小，避免错误路径导致不受限的内存读取。
- Telegram 启动数据增加群聊来源拒绝逻辑，并增加相应单测。
- 补丁安装器限定已审核上游 HEAD、`smgsp6/3x-ui` 的 Git origin，并拒绝修改 `main` 和脏工作树。
- 新增 `.gitignore` 敏感目录规则。
- 修复 `internal/web/controller/miniapp.go` 中 `service` 缺失的编译导入。

以上测试不能代替完整仓库的 Go/React 构建验证，Docker 正式发行仍待完成。
