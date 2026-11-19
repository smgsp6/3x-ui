"""Prepare the fixed manual beta build from explicitly reviewed input bytes."""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

BASES = {
    "frontend": "docker.io/library/node",
    "builder": "docker.io/library/golang",
    "runtime": "docker.io/library/alpine",
}
ASSETS = {
    "Xray-linux-64.zip": "https://github.com/XTLS/Xray-core/releases/download/v26.11.9/",
    "mtg-multi-1.16.1-linux-amd64.tar.gz": "https://github.com/mhsanaei/mtg-multi/releases/download/v1.16.1/",
    **{name: "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/download/"
       for name in ("geoip.dat", "geosite.dat")},
    **{name: "https://github.com/chocolate4u/Iran-v2ray-rules/releases/download/"
       for name in ("geoip_IR.dat", "geosite_IR.dat")},
    **{name: "https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/download/"
       for name in ("geoip_RU.dat", "geosite_RU.dat")},
}
HEX = r"[0-9a-f]{64}"


def require(value, message):
    if not value:
        raise ValueError(message)


def replace_once(text, pattern, replacement):
    result, count = re.subn(pattern, lambda _: replacement, text, flags=re.M)
    require(count == 1, "fixed recipe no longer matches its reviewed shape")
    return result


def prepare(lock, approved_hash, inputs, context):
    require(re.fullmatch(HEX, approved_hash), "approved lock SHA-256 is required")
    content = lock.read_bytes()
    require(hashlib.sha256(content).hexdigest() == approved_hash, "input lock digest mismatch")
    data = json.loads(content)
    require(set(data) == {"bases", "files"}, "unexpected lock fields")
    require(set(data["bases"]) == set(BASES), "all three base images must be pinned")
    for key, repo in BASES.items():
        require(re.fullmatch(re.escape(repo) + r"@sha256:" + HEX, data["bases"][key]),
                "base image must use an approved official repository and digest")
    destination = context / "vela-reviewed-inputs"
    destination.mkdir()
    seen = set()
    for name, entry in data["files"].items():
        url, digest = entry["url"], entry["sha256"]
        if name in ASSETS:
            prefix = ASSETS[name]
            suffix = url.removeprefix(prefix)
            require(url.startswith(prefix) and re.fullmatch(r"(?!latest/)[A-Za-z0-9._/-]+", suffix)
                    and not any(piece in {"", ".", "..", "latest"} for piece in suffix.split("/")),
                    "artifact source must use an explicit upstream release")
            if prefix.endswith(("v26.11.9/", "v1.16.1/")):
                require(suffix == name, "wrong upstream binary release asset")
        else:
            require(re.fullmatch(r"(builder|runtime)/[A-Za-z0-9_.+-]+\.apk", name),
                    "unrecognized build input")
            parsed = urlsplit(url)
            require(parsed.scheme == "https" and parsed.netloc == "dl-cdn.alpinelinux.org"
                    and re.fullmatch(r"/alpine/v\d+\.\d+/(main|community)/x86_64/[^/]+\.apk", parsed.path)
                    and not parsed.query and not parsed.fragment and parsed.path.endswith("/" + Path(name).name),
                    "APK must come from a versioned official Alpine repository")
            seen.add(name.split("/")[0])
        require(re.fullmatch(HEX, digest), "missing file digest")
        source = inputs / name
        require(source.is_file() and not source.is_symlink() and source.resolve().is_relative_to(inputs.resolve()),
                "reviewed input file is missing or unsafe")
        target = destination / name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, target)
        with target.open("rb") as file:
            require(hashlib.file_digest(file, "sha256").hexdigest() == digest, "build input digest mismatch")
    require(set(ASSETS) <= set(data["files"]) and seen == {"builder", "runtime"}, "input lock is incomplete")

    recipe = context / "VelaCandidateDockerfile"
    text = recipe.read_text()
    for key, pattern, suffix in (
        ("frontend", r"^FROM --platform=\$BUILDPLATFORM node:26-alpine AS frontend$", " AS frontend"),
        ("builder", r"^FROM golang:1\.27-alpine AS builder$", " AS builder"),
        ("runtime", r"^FROM alpine$", ""),
    ):
        text = replace_once(text, pattern, f"FROM {data['bases'][key]}{suffix}")
    for stage, pattern in (
        ("builder", r"^RUN apk --no-cache --update add \\[\s\S]*?  unzip$"),
        ("runtime", r"^RUN apk add --no-cache --update \\[\s\S]*?  openssl \\$"),
    ):
        continuation = " \\" if stage == "runtime" else ""
        text = replace_once(text, pattern,
                            f"RUN --network=none --mount=type=bind,source=vela-reviewed-inputs/{stage},target=/reviewed "
                            f"apk add --no-network --no-cache /reviewed/*.apk{continuation}")
    text = text.replace("RUN npm ci --ignore-scripts --no-audit --no-fund",
                        "RUN npm ci --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org")
    text = text.replace("RUN go build ", "RUN GOPROXY=https://proxy.golang.org GOSUMDB=sum.golang.org GOTOOLCHAIN=local go build -mod=readonly ")
    anchor = 'RUN ./DockerInit.sh "$TARGETARCH" "$TARGETVARIANT"'
    text = replace_once(text, "^" + re.escape(anchor) + "$",
                        'RUN --network=none --mount=type=bind,source=vela-reviewed-inputs,target=/reviewed '
                        './DockerInit.sh "$TARGETARCH" "$TARGETVARIANT"')
    recipe.write_text(text)

    # Preserve the pinned MTG archive verifier. Replace retrieval with copies
    # from the already verified build-context bundle after the CI pinning step.
    init = context / "DockerInit.sh"
    initial = init.read_text()
    mapping = [
        ('curl -sfLRO "https://github.com/XTLS/Xray-core/', 'cp /reviewed/Xray-linux-64.zip .'),
        ('curl -sfLRO "https://github.com/mhsanaei/mtg-multi/', 'cp /reviewed/mtg-multi-1.16.1-linux-amd64.tar.gz .'),
    ]
    for needle, replacement in mapping:
        initial = replace_once(initial, "^" + re.escape(needle) + ".*$", replacement)
    # Keep the CI pin and its verifier while replacing the network download.
    old_helper = "RUN sh deploy/vela/ci_pin_mtg_dockerinit.sh DockerInit.sh\n"
    require(text.count(old_helper) == 1, "MTG pinning step missing")
    recipe.write_text(text.replace(old_helper, ""))
    version = next(line for line in initial.splitlines() if line.startswith("MTG_MULTI_VER="))
    initial = replace_once(initial, "^" + re.escape(version) + "$", "MTG_MULTI_VER=v1.16.1")
    initial = replace_once(initial, r'^tar -xzf "\$\{MTG_PKG\}\.tar\.gz"$',
                           'sh /app/deploy/vela/ci_verify_mtg_archive.sh "$PLATFORM" "${MTG_PKG}.tar.gz"\n'
                           'tar -xzf "${MTG_PKG}.tar.gz"')
    for name in ("geoip.dat", "geosite.dat", "geoip_IR.dat", "geosite_IR.dat", "geoip_RU.dat", "geosite_RU.dat"):
        if "_" in name:
            pattern = rf"^curl -sfLRo {re.escape(name)} .*$"
        else:
            pattern = rf"^curl -sfLRO https://github.com/Loyalsoldier/[^ ]+/{re.escape(name)}$"
        initial = replace_once(initial, pattern, f"cp /reviewed/{name} .")
    require("curl " not in initial, "unexpected network retrieval in DockerInit")
    init.write_text(initial)
    return data["bases"]["runtime"]


if __name__ == "__main__":
    print(prepare(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])))
