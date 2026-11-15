# Vela 发行签名方案（第七阶段开发预览）

**尚未建立生产签名密钥、没有 Vela 正式 `stable.json`，也没有通过生产发布审核。** 本文仅定义正式发布前必须完成的签名流程；不得把示例当作已经批准的发布。

## 信任边界

- 维护者在**离线受控设备**上建立独立的 Ed25519 签名私钥。**私钥不能进入 Git、GitHub Actions 构建上下文、Docker 镜像、Telegram 消息或服务器安装包。**
- 经独立渠道核对公钥后，将其 SHA256（PEM 文件字节）**写死在经过代码审查的 `deploy/vela/vela` 中**，替换目前的 `UNCONFIGURED-RELEASE-SIGNING-KEY` 占位值。该改动需通过 PR 审查；不可使用运行时环境变量、下载的 JSON 来替代信任锚。
- 安装 Vela 时从已审核的安装包分发公钥到本机 `<VELA_HOME>/release-public.pem`。更新器会首先比对公钥指纹，再检查 `.sig` 的 Ed25519 数字签名，之后才读取 `stable.json` 中的镜像摘要。
- `stable.json` 与 `stable.json.sig` 可放在公开 Fork 的 `deploy/vela/`；签名可公开，私钥绝不可公开。
- 镜像必须来自 `ghcr.io/smgsp6/3x-ui@sha256:<64 位摘要>`；签名证明**发行清单**出自维护者，并不能单独证明镜像构建过程安全。镜像来源、构建材料和镜像层仍须独立审计。

## 仅供维护者在受控离线环境演练

```bash
# 生成生产签名密钥之前，应先完成独立密钥管理与备份方案审核。
openssl genpkey -algorithm Ed25519 -out /secure/offline/vela-release-private.pem
chmod 600 /secure/offline/vela-release-private.pem
openssl pkey -in /secure/offline/vela-release-private.pem -pubout -out release-public.pem
sha256sum release-public.pem

# stable.json 中必须固定仓库、stable 频道、不可变 digest，
# 还要携带单调递增的正整数 releaseSequence。
# 签名精确覆盖 JSON 文件原始字节（不要在签名后修改空白符或换行）。
openssl pkeyutl -sign -rawin -inkey /secure/offline/vela-release-private.pem -in stable.json -out stable.json.sig
openssl pkeyutl -verify -pubin -inkey release-public.pem -rawin -in stable.json -sigfile stable.json.sig
```

第八阶段开发中的签名清单结构例子（以下 Digest 是虚构测试值，不可发布）：

```json
{
  "repository": "smgsp6/3x-ui",
  "channel": "stable",
  "releaseSequence": 1,
  "image": "ghcr.io/smgsp6/3x-ui@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

客户端把已接受的正整数发行序号保存在本地 `release.sequence`，新签名清单序号必须不低于已安装版本；相同序号不能改指其他镜像。发生故障恢复时恢复旧序号。该防护**不能替代独立的公钥撤销和真正的发行审批**。

上述路径均为示例；**不要在公开仓库目录生成私钥。** 正式版本还需要密钥轮换、撤销、防重放的真实部署演练、生产环境审批、主机真实部署验收和多节点金丝雀更新流程。

## 当前故意不可用

第七阶段维护工具把 `RELEASE_KEY_SHA256` 设为 `UNCONFIGURED-RELEASE-SIGNING-KEY`，`vela update` 在此状态下**直接拒绝执行**，不会下载清单、拉取镜像或停止服务器。测试代码使用运行时临时产生的测试私钥，仅用来验证正常签名和签名损坏时的行为，**不与用户或公开安装包共享测试私钥**。
