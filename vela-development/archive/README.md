# Vela 开发源码存档（第十二阶段）

此目录保存 Vela 第十二阶段的**完整开发预览源码 ZIP**，用于防止 ChatGPT 对话附件失效、方便未来续接项目。

- 完整包：[vela-phase12-dev-preview.zip](./vela-phase12-dev-preview.zip)
- 文件字节数：`1271482`
- SHA256：`3d0c33a8c7d046a4f00527687eec64efe179f8a3ede957de05d0ea57395de0fd`
- Git Blob SHA：`d1427bdd1a7a86606a1fa86245b443c79e974d72`
- 原版基线：`5297fd3c8495d80fab97ae511553fa545c69e913`
- 目标：`smgsp6/3x-ui` 的 `vela-dev` 开发分支
- 项目续接档案：[PROJECT-CONTINUITY.md](../docs/PROJECT-CONTINUITY.md)
- 测试报告：[PHASE12-TEST-REPORT.md](../docs/PHASE12-TEST-REPORT.md)

ZIP 内包含 `apply_to_repo.py`、`internal/`、`frontend/`、`deploy/`、`tests/`、`brand/`、`docs/` 等源文件，**不是可直接运行的部署包**。目前仅在离线测试中验证了安全模块和模拟升级流程；完整 Go/React 构建、真实 Docker 镜像和 Telegram 实机验收尚未完成。

请勿将此存档直接覆盖 `main`，不要上传任何服务器运行数据、数据库、私钥、Bot Token 或 `.env`。正式部署应等待完整集成测试及安全审计通过。

## 每次续接项目
先读取本目录 ZIP 的 `docs/PROJECT-CONTINUITY.md`、`README.md` 和实际代码，再评估接下来的修改，不要假定源码已经合并进根目录。
