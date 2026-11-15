# Vela 第十二阶段实测报告（2026-11-15）

**结论：局部源码、单元测试与离线补丁/升级模拟通过，但不是完整项目构建或 Docker/Telegram 实机验收。不可用于生产安装。**

| 检查 | 实际结果 | 范围/限制 |
|---|---|---|
| 第十一阶段继承的 Python 离线整组回归 | **73 / 73** | `python3 -m unittest discover -s tests -p 'test_*.py' -v`，启动时还未加入本阶段 3 项新契约测试；196.880 秒；假 Docker、合成 Git 源树、扫描器测试 |
| 本阶段新增的安全契约测试 | **3 / 3** | 检查 Go Secret 校验、TLS SAN 身份保持、补丁复制的实际源码及新增文档 |
| 本阶段合计 Python 测试 | **76 / 76** | 73 项整套和 3 项增量分别运行，没有把新增测试混入先前整套结果 |
| Go `tgminiapp` 独立包 | **通过** | `GO111MODULE=off go test -race -count=2 ./internal/web/service/tgminiapp`，包括新增的宽松文件权限、危险目录、非法内容、错域证书、SAN/IP/CN 检查 |
| Go vet | **通过** | 仅 `internal/web/service/tgminiapp`，不代表整仓 |
| Python 与 Bash 语法 | **通过** | 补丁、维护命令、审计器和 Python 单元测试文件 |
| GitHub Fork 实际源代码锚点只读对照 | **22 / 22 唯一匹配** | 对每个原版待修改文件抽取一个关键锚点进行 `fetch_file` 唯一性检查；不是逐个全段替换或实仓完整构建 |

## 隐私说明

- 当前开发交付包仅含源码、测试占位数据、公开 Logo、Docker/CI 模板与文档。未接触实际服务器密钥或数据库。
- 不应把“特征扫描无命中”描述为所有形式的私密数据都不存在。完整 Git 历史、builder 缓存、最终镜像以及运行容器网络出口审计**尚未完成**。
- 更新器依然因没有正式签名发布密钥和已审计镜像而主动拒绝生产更新；这不是故障。

## 无法在本地完成的发布门禁

- 环境只有 Go 1.23.2、Node 22，缺 Docker 且无法直接 DNS 克隆 GitHub；目标项目要求 Go 1.27.4 和 Node 26。
- 因此前端完整 `npm ci/typecheck/test/build`、`go test ./...`、完整 Go 编译、Docker build/save 层扫描、真实 Telegram Mini App WebView 与 ACME 续签都仍需在可信 CI/测试 VPS 验收。
- GitHub 写入此前返回 403，开发包没有提交至 `smgsp6/3x-ui`。

## 本阶段重要安全行为

- Secret 路径即使在绕过安装脚本、甚至文件被替换的情况下，也不能被其他用户读取或修改；后端通过 `Lstat`/`Fstat` 身份比对、权限/父目录检查和单行格式拒绝异常读取。
- 同域 ACME 续签可继续热加载；未经审查的不同 DNS/IP/CN 身份证书被拒绝自动替换。主动换域名应按单独的配置变更流程操作。