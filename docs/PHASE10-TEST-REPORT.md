# 第十阶段测试报告

本报告以第十阶段本地实际命令结果为准。最终结果见文末。

## 测试范围

- 标准库独立模块：`GO111MODULE=off go test -race -count=1 ./internal/web/service/tgminiapp`
- Go vet：`GO111MODULE=off go vet ./internal/web/service/tgminiapp`
- 补丁应用：`python3 -m unittest discover -s tests -p 'test_apply_to_repo.py'`
- 证书前后端契约：`python3 -m unittest discover -s tests -p 'test_certificate_contract.py'`
- 维护脚本、隐私扫描、历史扫描：单独执行可用的本地模拟测试。
- TypeScript 语法解析：使用本地 TypeScript 转译器；**不等同完整 React 类型检查**。

## 发布前仍需要

真实 Go/Node 全仓构建、Docker 镜像、Telegram 内登录、真实 ACME 续签后的 TLS 握手、证书可信链、数据备份回滚、多节点联调与 Git 全历史审计。

## 第十阶段本次实测结果（2026-11-15）

| 实测项目 | 结果 | 说明 |
|---|---|---|
| Go 独立安全模块 `go test -race -count=5` | **通过** | 含实际本地 TLS 无 SNI 握手、续签切换、半写入回退、过期/未来/倒退证书拒绝、并发回调 |
| Go vet | **通过** | 仅 `tgminiapp` 独立 Go 模块，不能代表整仓静态分析 |
| 维护升级模拟测试 | **37 / 37 通过** | 耗时约 196 秒；使用假的 Docker/HTTP，非真实 VPS |
| 补丁保护模拟测试 | **9 / 9 通过** | 加入临时文件符号链接与父目录符号链接拒绝测试 |
| 证书 API/前端契约测试 | **3 / 3 通过** | 静态跨文件契约断言，非真实 React 集成测试 |
| 隐私审计器单元测试 | **9 / 9 通过** | 仅工具规则的离线测试 |
| Git 历史审计器单元测试 | **3 / 3 通过** | 不是用户 Fork 的全历史扫描 |
| TypeScript transpile 语法检查 | **3 个新增 TSX 文件通过** | 本地 TypeScript 5.8.3；不是上游 Node 26 / TS 7 完整类型检查 |
| 包内高置信度私钥/Telegram Token 模式扫描 | **69 个文件，0 项匹配** | 只对本轮交付目录内文件；不是完整密钥扫描或镜像层检查 |
| Bash/Python 语法检查 | **通过** | 不代表运行时或 Docker 环境通过 |

**Python 合计 61 / 61 个测试通过。** Go Race 为另一个独立检查。完整 Go/React 构建和生产环境验证未完成，不能发布生产一键安装命令。
