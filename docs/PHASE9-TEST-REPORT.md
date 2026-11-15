# Vela 第九阶段实际验证记录

时间：2026-11-15。以下为离线开发环境执行的真实测试结果，**不是生产服务器验证**。

| 检查 | 结果 | 真实覆盖范围 |
|---|---|---|
| `GO111MODULE=off go test -race -count=1 ./internal/web/service/tgminiapp` | **通过** | Telegram initData、管理员名单、证书读元信息、新增提醒逻辑的 Go 独立单元测试 |
| `GO111MODULE=off go vet ./internal/web/service/tgminiapp` | **通过** | 上述独立 Go 包静态检查 |
| `python3 -m unittest ... test_apply_to_repo.py` | **7/7 通过** | 合成 Fork 上补丁应用、权限、防止覆盖其他仓库、私聊按钮及定时器接入的静态测试 |
| `python3 -m unittest ... test_privacy_audit.py` | **9/9 通过** | 隐私扫描器的离线单元测试 |
| `python3 -m unittest ... test_git_history_audit.py` | **3/3 通过** | Git 历史扫描器的测试；并未扫描真实 Fork 完整历史 |
| 第八阶段升级器精选回归 | **4/4 通过** | 签名篡改拒绝、旧版重放拒绝、更新失败的数据库恢复、断电后的恢复（虚拟 Docker） |
| React/TSX transpile 语法检查 | **通过** | 3 个新增 TSX 页面；不等于 `tsc --noEmit` 或 Vite 编译 |
| Bash/Python 语法检查 | **通过** | 运维脚本和补丁工具 |
| 隐私扫描器直接审计本开发包 | **未执行成功，按设计拒绝** | 目录不是可读 Git 工作树；改由合成 Git 仓库应用补丁后审计通过，不能代表真实 Fork |
| Docker、Telegram WebView、Go/Node 全项目 | **未执行** | 当前环境没有 Docker，Go 版本 1.23.2、Node 22.16.0 低于上游要求 |

## 发现并修复的兼容风险

- 原版 `internal/web/web.go` 的 `GetDiscordBotEnable()` 语句实际出现 **两次**；第九阶段改为绑定后面的 `s.discordGateway != nil` 唯一代码块，避免错误插入或因多处匹配而中止。
- Telegram 启动前错误读取原版数据库 Bot Token、Secret 缺失错误返回不明确；现在 Vela 模式仅从 Secret 读取且失败时明确返回错误。
- `homeRows` 现在接受 chatID，并且只为获授权的管理员私聊插入 Telegram Mini App 按钮。

## 发布前仍然必做

- 用户 Fork 实际开发分支套用补丁并执行 `gofmt`、`go test ./...`、React `npm run typecheck && npm run build`。
- Docker 构建上下文、最终镜像层、Git 完整历史、CI 日志隐私审计。
- 实际 Telegram 私聊和不同设备 Mini App 端到端测试；非法聊天/冒充管理员的拒绝测试。
- 实际证书签发续签、到期提醒、时区和容器重建后去重验证。
- 多节点/Xray 的 API、动态入站、数据库迁移、升级前备份与回滚实机验证。
- 正式发行密钥与已审计的 SHA256 镜像发布。只有以上通过才能提供生产一键安装。
