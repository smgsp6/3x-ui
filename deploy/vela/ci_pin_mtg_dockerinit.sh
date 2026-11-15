#!/bin/sh
# Development-only: pin the official mtg-multi asset in Docker's builder stage.
# The Git source file remains untouched to reduce upstream update conflicts.
set -eu
[ "$#" -eq 1 ] || exit 2
source=$1
[ -f "$source" ] && [ ! -L "$source" ] || exit 2
expected=$(cat <<'AUDITED_SOURCE'
MTG_MULTI_VER=$(curl -sfL "https://api.github.com/repos/mhsanaei/mtg-multi/releases/latest" | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n 1)
AUDITED_SOURCE
)
actual=$(grep '^MTG_MULTI_VER=' "$source" || true)
[ "$actual" = "$expected" ] || {
    echo "Vela: upstream MTG version source changed; manual review needed" >&2
    exit 2
}
needle='tar -xzf "${MTG_PKG}.tar.gz"'
[ "$(grep -Fxc "$needle" "$source" || true)" -eq 1 ] || exit 2
url='curl -sfLRO "https://github.com/mhsanaei/mtg-multi/releases/download/${MTG_MULTI_VER}/${MTG_PKG}.tar.gz"'
[ "$(grep -Fxc "$url" "$source" || true)" -eq 1 ] || exit 2
temporary=$(mktemp "$(dirname "$source")/.vela-pinned-mtg-XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
sed 's/^MTG_MULTI_VER=.*/MTG_MULTI_VER=v1.16.1/' "$source" |
    awk '
    $0 == "tar -xzf \"${MTG_PKG}.tar.gz\"" {
        print "sh /app/deploy/vela/ci_verify_mtg_archive.sh \"$PLATFORM\" \"${MTG_PKG}.tar.gz\""
    }
    {print}
    ' > "$temporary"
[ "$(grep -Fc 'ci_verify_mtg_archive.sh' "$temporary" || true)" -eq 1 ] || exit 2
chmod 755 "$temporary"
mv -f -- "$temporary" "$source"
echo "Vela: official mtg-multi v1.16.1 pinned with SHA256 verification"
