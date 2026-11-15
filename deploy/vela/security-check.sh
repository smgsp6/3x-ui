#!/usr/bin/env bash
# Scan public tracked files for high-confidence accidental secrets.
# Fail-closed helper; not a substitute for gitleaks, CodeQL, govulncheck or review.
set -Eeuo pipefail

repo="${1:-.}"
[[ -d "$repo/.git" || -f "$repo/.git" ]] || { echo 'ERROR: 目标不是 Git 仓库' >&2; exit 2; }
cd "$repo"
origin=$(git remote get-url origin)
case "$origin" in
  https://github.com/smgsp6/3x-ui|https://github.com/smgsp6/3x-ui.git|git@github.com:smgsp6/3x-ui|git@github.com:smgsp6/3x-ui.git|ssh://git@github.com/smgsp6/3x-ui|ssh://git@github.com/smgsp6/3x-ui.git) ;;
  *) echo 'ERROR: 拒绝扫描其他项目。只允许 smgsp6/3x-ui。' >&2; exit 2;;
esac
bad=0
while IFS= read -r path; do
  case "$path" in
    .env|.env.*|*.key|*.p12|*.pfx|*.db|*.db-wal|*.db-shm|*private*.pem|*backup*.sql|*backup*.dump)
      echo "UNSAFE tracked path: $path" >&2
      bad=1 ;;
  esac
done < <(git ls-files)
# Restrict key content scanning to tracked files; --binary ignored by git grep.
if git grep -Il -E -- '-----BEGIN (RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----' -- ':!**/*_test.go' ':!**/*test*' ':!docs/**' 2>/dev/null | grep -q .; then
  echo 'UNSAFE: tracked non-test file contains a PEM private-key header.' >&2
  bad=1
fi
if [[ "$bad" -ne 0 ]]; then
  echo 'FAIL: 请从 Git 历史和服务器配置中审查敏感数据。不要直接发布。' >&2
  exit 1
fi
printf 'OK: 没有检测到预设的高置信度敏感文件路径。仍需使用完整密钥扫描器。\n'
