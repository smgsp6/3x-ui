# Vela 单一私有内测镜像

构建固定源码 `9ef190a504221c95925b5224005355bd1313c147`，引用其四项通过的 [CI 44491849398](https://github.com/smgsp6/3x-ui/actions/runs/44491849398)。使用主人批准的独占 Linux amd64 Docker 主机。仅允许本机默认 Unix socket。验证使用另一台独立 Docker 主机。无需修改 GitHub 默认分支。

## 放行条件

- 主人明确指定唯一发布账号与本次固定标签，并确认现有 `ghcr.io/smgsp6/3x-ui` 包为 Private、账号具有该包的必要权限、遵守私有包存储和传输额度。只读查验出现 403、404 或未知时停止。GitHub 包设置中的授权范围需由所有者复核。
- 审核人与操作者核对交付脚本的完整 Git 提交 SHA、构建输入锁的 SHA-256、三项官方 amd64 基础镜像 manifest、下载文件的原始出处及摘要。APK 根据基础镜像的 Alpine 版本准备完整依赖闭包，安装仍须通过 Alpine 签名检查。扫描工具使用主人核实的 Trivy 二进制和最新可获得的官方漏洞数据库，记录来源、日期和两个摘要。
- 只使用独占 Docker 主机，无现存容器或其他写入者。测试生成合成资料，并调用同一候选源码的 HTTPS/Xray 与 Compose/SQLite 恢复用例。恢复测试需要本机 sudo 与默认 Docker socket。
- 不生成正式签名，不创建包，不修改可见性，不覆盖候选标签。包管理者在发布期间应暂停可能冲突的手动写入。存在同名标签时，停止并审查已有 manifest。

## 手动顺序

1. 准备两个干净 checkout。工具 checkout 固定到审核并由主人批准的完整交付提交。源码 checkout 的本地分支名为 `vela-dev`，HEAD 固定为候选源码 SHA。配置 `APPROVED_DELIVERY_SHA` 为工具提交，`VELA_EXCLUSIVE_DOCKER=YES`。使用一个当前用户所有、权限 0700 的 `XDG_RUNTIME_DIR`，并令 `VELA_BUILD_EVIDENCE` 等于该目录下的 `vela-beta-evidence`。
2. 使用授权凭据运行工具的 `precheck`。设置 `VELA_INPUT_LOCK` 指向获批的 JSON 文件、`APPROVED_INPUT_LOCK_SHA256` 为其摘要、`VELA_INPUT_DIR` 为逐文件校验的素材目录。锁包含 `bases` 和 `files` 两个对象。`bases` 的键是 `frontend`、`builder`、`runtime`，值是 `docker.io/library/{node,golang,alpine}@sha256:…` 对应的完整引用。`files` 以相对文件名为键，值包含版本化官方 `url` 与文件 `sha256`。必需文件以 `beta-inputs.py` 的 ASSETS 为准，另外包含 `builder/*.apk` 和 `runtime/*.apk` 两组依赖闭包。设置 `APPROVED_TRIVY_SHA256`、`TRIVY_CACHE_DIR` 和 `APPROVED_TRIVY_DB_SHA256`，分别对应扫描器、本地缓存目录和其中 `db/trivy.db` 的摘要。构建工具需要 Bash、Docker/Compose/Buildx、Python 3.11+ 与经审核的 PyYAML、Node/npm、Go 1.27.4、jq、gh、OpenSSL 和 flock。
3. 在源码 checkout 中以绝对路径运行已审核工具 `bash /path/to/tool/deploy/vela/beta-image.sh build`。只有锁定输入、全镜像层扫描、依赖及镜像漏洞扫描、HTTPS、Xray TCP/UDP 与恢复全部成功，才写入同一 daemon 的配置摘要证据。构建阶段无需 GHCR 凭据。
4. 同一独占 daemon 上以获批账号和包写入凭据设置 `GH_TOKEN`、`APPROVED_PUBLISHER`，明确授权后运行 `bash /path/to/tool/deploy/vela/beta-image.sh publish PUBLISH-PRIVATE-BETA`。记录配置摘要、发布 manifest Digest 及发布 Docker ID。发布成功仍待独立验证。
5. 独立主机使用相同获批交付代码，配置本机独占 daemon 和私有运行目录。提供只读包凭据、`EXPECTED_CONFIG_ID`、`EXPECTED_PUSH_DIGEST` 和 `PUBLISH_DOCKER_ID`，执行 `bash /path/to/tool/deploy/vela/beta-image.sh verify`。只有远端 manifest 与推送记录一致，且按 Digest 拉取的配置摘要、源码标识和 Private 核验都通过，才能把输出的 `ghcr.io/smgsp6/3x-ui@sha256:…` 交给隔离主机预检。任一步失败应保留摘要和日志供审查，停止部署。不要覆盖已有标签或自动删除包。
