# Vela 第十一阶段测试报告（2026-11-15）

本阶段以实际运行的本地测试为准。**所有以下离线用例通过，但完整 Go/React 项目构建及真实 Docker 镜像构建尚未执行。**

| 项目 | 实际结果 | 验证范围 |
|---|---:|---|
| Docker 维护、升级与恢复模拟 | 37/37 | 假 Docker/HTTP 环境；整套耗时约 198.6 秒 |
| 补丁应用／失败恢复 | 9/9 | 合成 Git 工作树、文件权限和异常路径 |
| CI 构建顺序与 TLS 回退契约 | 5/5 | 静态工作流检查与应用后代码检查 |
| Telegram 原始备份外传拦截 | 1/1 | 补丁应用后检查手动、定时、API、底层文件发送入口 |
| Docker 镜像层隐私扫描器 | 6/6 | 合成 docker-save TAR 层：已删除敏感文件、Token、私钥等 |
| 证书接口契约 | 3/3 | 前后端响应结构静态匹配 |
| 本地隐私扫描器 | 9/9 | 扫描规则测试 |
| Git 历史审计器 | 3/3 | 扫描器测试，不是仓库全部历史实际审计 |
| **Python 离线测试合计** | **73/73** | 上述用例分别运行，未将模拟环境等同生产部署 |
| Go 独立安全模块 Race | 通过 | `GO111MODULE=off go test -race -count=2 ./internal/web/service/tgminiapp` |
| Go vet | 通过 | 仅 `internal/web/service/tgminiapp` |
| TypeScript transpile | 3/3 | 三个新增 TSX 文件语法；不是完整类型检查 |
| Shell/Python 语法与 YAML 格式 | 通过 | Vela CLI、预检查、隐私审计、镜像扫描及 Actions YAML |

## 新门禁将检查什么

1. 从 **`smgsp6/3x-ui`** 干净工作树完整抓取 Git 历史、执行隐私审计（没有生产密钥）。
2. 安装 Go 1.27.4 和 Node 26，先完成 `npm ci`、React 类型检查、前端单测、Vite 构建，断言 `internal/web/dist/{index,miniapp,login}.html` 存在。
3. 后续执行 `go test ./...`、Go Race、Go 可执行文件构建和依赖漏洞扫描。
4. 只有以上成功才执行 **不会推送的 Docker 构建**，并使用 `docker image save | image_layer_audit.py --stdin` 扫描全部最终镜像层。

## 仍然阻止发布的事项

- 新 GitHub Actions **尚未提交和运行**：GitHub 连接此前写入权限 403，本地未安装原仓 Go 1.27.4/Node 26/Docker，不能宣称整仓编译通过。
- 本扫描器检测最终镜像层，**不能证明构建阶段缓存、公开历史、外部基础镜像、真实运行容器或第三方网络出口全部安全**；需要额外人工/自动审计。
- 证书独立签发/主动续签、Telegram 实机登录、HTTPS 反向代理、Xray 多节点和完整一键安装仍未完成。
- `vela update` 仍无正式发行公钥与签名镜像，安全设计明确拒绝生产更新。
- 修改仅存在本地代码包，不是已提交 GitHub 的成品。
