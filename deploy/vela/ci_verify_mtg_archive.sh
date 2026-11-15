#!/bin/sh
# GitHub official release asset digests for mhsanaei/mtg-multi tag v1.16.1.
# Refuse all altered or unknown archives; never echo downloaded binary bytes.
set -eu
[ "$#" -eq 2 ] || exit 2
[ "$2" = "mtg-multi-1.16.1-linux-$1.tar.gz" ] || exit 2
case "$1" in
  386) sha=b96d0c54211dd775aeb92515fb97874a9a479276025b9ed24c054eb3e9ad40de ;;
  amd64) sha=c4a0ee4b6652530d93d9cfdb171492678dff1dbbed9d5702f6d72de8b132d167 ;;
  arm64) sha=9a296cb8785f7a36d18b2537e7133757f09422dc033a5c42ea35d1b6b37e05af ;;
  armv6) sha=b3945676a2163a81361d758e9637ffc7185a57130b90a9fac47fb8612de8423c ;;
  armv7) sha=89590ae8b4162a42418704c8b358dafaab8ec324b48cd02f95f30d91b6c84008 ;;
  *) exit 2 ;;
esac
if ! printf '%s  %s\n' "$sha" "$2" | sha256sum -c - >/dev/null 2>&1; then
  echo "Vela: mtg-multi archive digest mismatch; refusing build" >&2
  exit 1
fi
echo "Vela: official mtg-multi archive digest verified"
