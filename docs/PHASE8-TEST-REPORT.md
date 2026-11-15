# Vela 第八阶段实际验证结果

> 本文仅记录当前开发容器的离线测试；不是生产 VPS 上的验收，不代表公开仓库或 Docker 镜像无漏洞。

## 验证范围与结果

| 测试 | 第八阶段结果 | 说明 |
| --- | --- | --- |
| Go `tgminiapp` 独立安全模块 | **通过** | `GO111MODULE=off go test -race -count=1 ./internal/web/service/tgminiapp`；另有 `go vet` 通过 |
| 源码/构建目录隐私扫描器单元测试 | **9/9 通过** | 离线模拟，不是实际 Docker 构建上下文扫描 |
| Git 历史隐私扫描器单元测试 | **3/3 通过** | 测试仓库模拟，不是用户 Fork 全历史审计 |
| 应用补丁保护测试 | **6/6 通过** | 模拟 Fork 审核分支中应用/回滚、文件复制失败、接入隐私扫描 |
| 维护升级器测试 | **37/37 通过** | 降低并发分组重跑，完整覆盖签名版本序号、防旧清单重放、故障恢复 |
| Bash 语法检查 | **通过** | `bash -n deploy/vela/vela deploy/vela/preflight.sh deploy/vela/security-check.sh` |
| Python 语法检查 | **通过** | 本阶段修改与隐私工具 |
| 整仓 Go/React + Docker 实机 + Telegram WebView | **尚未执行** | 缺少相应构建环境与生产发行签名 |

## 本阶段验证细节

- **37 项维护测试**：第一轮并行运行遇到 20 秒单项超时；降低并发并把测试用例超时调整为 45 秒后，曾发现 1 项新夹具存在文件未清理的问题；修复后重新完整运行，最终输出为 **`SUMMARY 37 / 37`**（逐项进程隔离、虚拟 Docker/curl；不是实际 Docker 引擎）。
- **其他 Python 测试**：源码/构建目录隐私检查 9/9、可达 Git 历史扫描器 3/3、仓库补丁工具 6/6，合计 **55 项 Python 测试通过**。
- **Go 安全核心**：`GO111MODULE=off go test -race -count=1 ./internal/web/service/tgminiapp` 通过；`GO111MODULE=off go vet ./internal/web/service/tgminiapp` 通过。
- **静态打包检查**：对本阶段目录 61 个文件执行高置信度密钥特征扫描，未匹配到预设的私钥、Bot Token、常见访问密钥格式。此扫描**不覆盖其他格式、Git 历史、CI 日志或镜像层**，不能证明完全没有秘密。
- **补丁应用范围**：模拟 Git 仓库通过 `apply_to_repo.py --check` 和写入测试；**未在真实完整 Fork 工作树完成整仓编译**。

## 仍需通过的发布阻断项

完整 Go/Node 前后端构建、Docker 实机/镜像层审计、真实 Telegram Mini App 登录/权限、证书续签、真实 SQLite WAL 恢复、Xray 动态入站、多节点、Host Network/Fail2ban 影响、正式发布签名/CI/镜像及独立安全审核。

正式 `RELEASE_KEY_SHA256` 仍为禁用占位符，**此交付包不是一键安装或生产更新包**。
