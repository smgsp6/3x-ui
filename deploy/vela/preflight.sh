#!/usr/bin/env bash
# Vela development-phase deployment preflight: READ-ONLY. Does not install or update.
set -Eeuo pipefail
umask 077

fail() { printf 'Vela PRECHECK FAIL: %s\n' "$*" >&2; exit 1; }
warn() { printf 'Vela PRECHECK WARN: %s\n' "$*" >&2; }
ok() { printf 'Vela PRECHECK OK: %s\n' "$*"; }

[[ "${EUID}" -ne 0 ]] || warn "正在以 root 执行检测；此脚本无需 root。"
command -v docker >/dev/null 2>&1 || fail '未安装 Docker Engine；正式版安装器将提供可审核的自动安装步骤。'
docker compose version >/dev/null 2>&1 || fail '未安装 Docker Compose 插件。'
docker info >/dev/null 2>&1 || fail 'Docker 守护进程不可用，或当前用户无 Docker 访问权限。'
ok 'Docker Engine / Compose 可用'

file="${1:-.env}"
[[ -f "$file" ]] || fail "找不到私密配置文件 $file。请使用示例模板在服务器本地创建。"
[[ ! -L "$file" ]] || fail '拒绝使用符号链接配置文件。'
mode=$(stat -c '%a' "$file")
if [[ $((8#$mode & 8#077)) -ne 0 ]]; then
  fail "配置文件权限过宽（$mode）；运行 chmod 600 '$file'。"
fi
ok '私密配置文件权限检查通过（不会输出内容）'

# Only parse exact literal KEY=VALUE lines; do not source/untrusted-execute .env.
read_env() {
  local key="$1" line
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" == "$key="* ]] || continue
    printf '%s' "${line#*=}"
    return 0
  done < "$file"
  return 1
}

id=$(read_env XUI_TG_MINIAPP_ADMIN_IDS || true)
url=$(read_env XUI_TG_MINIAPP_URL || true)
tokenfile=$(read_env VELA_BOT_TOKEN_FILE || true)
# Compose uses $VELA_HOME/secrets/vela_bot_token; infer from the env file when
# no override is set. Never reveal the credential itself.
[[ -n "$tokenfile" ]] || tokenfile="$(cd -- "$(dirname -- "$file")" && pwd -P)/secrets/vela_bot_token"
[[ "$id" =~ ^[1-9][0-9]*(,[1-9][0-9]*)*$ ]] || fail 'XUI_TG_MINIAPP_ADMIN_IDS 必须是合法 Telegram 数字用户 ID，多个用逗号分隔。'
[[ "$url" =~ ^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[^?#[:space:]]*)?$ ]] || fail 'Mini App 地址必须是公开 HTTPS URL，不能带密码、查询参数或 #fragment。'
[[ "$tokenfile" != "" ]] || fail 'VELA_BOT_TOKEN_FILE 未配置；请使用私有的 Docker Secret 文件。'
[[ -f "$tokenfile" && ! -L "$tokenfile" ]] || fail 'Bot Token Secret 文件不存在或为符号链接。'
secretmode=$(stat -c '%a' "$tokenfile")
[[ $((8#$secretmode & 8#077)) -eq 0 ]] || fail 'Bot Token Secret 文件权限必须为 0600 或更严格。'
[[ $(wc -c < "$tokenfile") -le 512 ]] || fail 'Bot Token Secret 文件异常大。'
ok '管理员 ID、Mini App HTTPS URL、Docker Secret 文件权限检查通过'

printf '\nVela 仅通过开发前置检测：没有修改配置，也没有安装软件。\n'
printf '正式安装还需要：签名镜像、域名证书、Docker 网络、Telegram 实测、全量回归。\n'
