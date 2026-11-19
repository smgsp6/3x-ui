"""Stage only hash-bound public inputs for the private beta build VM."""
import hashlib
import json
import re
import shutil
import sys
import tarfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from importlib import import_module

recipe = import_module("beta-inputs")
GITHUB_CDN = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
MAX_DOWNLOAD = 512 * 1024 * 1024


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def metadata(item):
    require(all(isinstance(item.get(key), str) and item[key].strip()
                for key in ("version", "license", "known_vulnerabilities")),
            "each entry requires version, license and vulnerability review")


class AllowedRedirect(HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        final = urlsplit(newurl)
        require(final.scheme == "https" and final.netloc in self.hosts, "unexpected redirect")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if final.netloc != urlsplit(req.full_url).netloc:
            redirected.remove_header("Authorization")
        return redirected


def download(url, digest, destination, hosts, headers=None):
    require(re.fullmatch(recipe.HEX, digest), "download requires a SHA-256 digest")
    require(urlsplit(url).scheme == "https" and urlsplit(url).netloc in hosts,
            "unexpected source")
    opener = build_opener(AllowedRedirect(hosts))
    checksum = hashlib.sha256()
    total = 0
    with opener.open(Request(url, headers=headers or {}), timeout=60) as response:
        with destination.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                require(total <= MAX_DOWNLOAD, "archive exceeds download budget")
                checksum.update(chunk)
                output.write(chunk)
    require(checksum.hexdigest() == digest, "download digest mismatch")


def extract_member(archive, member_name, output, digest):
    with tarfile.open(archive, "r:*") as source:
        member = source.getmember(member_name)
        require(member.isfile() and 0 < member.size <= MAX_DOWNLOAD, "unexpected archive member")
        with source.extractfile(member) as content, output.open("wb") as stream:
            shutil.copyfileobj(content, stream)
    with output.open("rb") as content:
        require(hashlib.file_digest(content, "sha256").hexdigest() == digest, "member digest mismatch")


def stage(lock, root):
    require(set(lock) == {"bases", "files", "trivy", "db"}, "invalid reviewed lock fields")
    require(set(lock["bases"]) == set(recipe.BASES), "three base digests required")
    require(set(recipe.ASSETS) <= set(lock["files"]), "required release assets missing")
    for key, item in lock["bases"].items():
        metadata(item)
        require(re.fullmatch(re.escape(recipe.BASES[key]) + "@sha256:" + recipe.HEX, item["ref"]),
                "base image must use an approved official digest")
    apk_stages = set()
    for name, item in lock["files"].items():
        metadata(item)
        url = item["url"]
        if name in recipe.ASSETS:
            prefix = recipe.ASSETS[name]
            require(url.startswith(prefix), "unexpected release origin")
            suffix = url.removeprefix(prefix)
            require(re.fullmatch(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)?", suffix)
                    and all(part not in {".", "..", "latest"} for part in suffix.split("/")),
                    "a concrete release version is required")
            hosts = GITHUB_CDN
        else:
            require(re.fullmatch(r"(builder|runtime)/[A-Za-z0-9_.+-]+\.apk", name), "invalid package path")
            apk_stages.add(name.split("/")[0])
            require(re.fullmatch(r"https://dl-cdn\.alpinelinux\.org/alpine/v\d+\.\d+/(main|community)/x86_64/"
                                 + re.escape(Path(name).name), url), "unexpected APK origin")
            hosts = {"dl-cdn.alpinelinux.org"}
        destination = root / "inputs" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        download(url, item["sha256"], destination, hosts)
    require(apk_stages == {"builder", "runtime"}, "both APK closures required")

    trivy, db = lock["trivy"], lock["db"]
    for item in (trivy, db):
        metadata(item)
    require(re.fullmatch(r"https://github\.com/aquasecurity/trivy/releases/download/v([0-9.]+)/Trivy_\1_Linux-64bit\.tar\.gz",
                         trivy["url"], re.I), "versioned official Trivy release required")
    binary_archive = root / "trivy.tar.gz"
    download(trivy["url"], trivy["archive_sha256"], binary_archive, GITHUB_CDN)
    binary = root / "bin/trivy"
    binary.parent.mkdir()
    extract_member(binary_archive, "trivy", binary, trivy["binary_sha256"])
    binary.chmod(0o700)

    require(re.fullmatch(recipe.HEX, db["manifest_sha256"]), "Trivy database OCI manifest digest required")
    # Anonymous token limited to pulling the public official database. Never
    # send GitHub credentials to the registry or blob CDN.
    with build_opener(AllowedRedirect({"ghcr.io"})).open(
        "https://ghcr.io/token?service=ghcr.io&scope=repository:aquasecurity/trivy-db:pull", timeout=30
    ) as response:
        token = json.load(response)["token"]
    registry = "https://ghcr.io/v2/aquasecurity/trivy-db"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.oci.image.manifest.v1+json"}
    manifest_file = root / "db-manifest.json"
    download(f"{registry}/manifests/sha256:{db['manifest_sha256']}", db["manifest_sha256"],
             manifest_file, {"ghcr.io"}, headers)
    layers = json.loads(manifest_file.read_bytes())["layers"]
    require(len(layers) == 1 and layers[0]["digest"] == f"sha256:{db['archive_sha256']}",
            "unexpected Trivy DB descriptor")
    database_archive = root / "trivy-db.tar.gz"
    download(f"{registry}/blobs/sha256:{db['archive_sha256']}", db["archive_sha256"],
             database_archive, {"ghcr.io", "pkg-containers.githubusercontent.com"}, headers)
    db_path = root / "trivy-cache/db"
    db_path.mkdir(parents=True)
    extract_member(database_archive, "trivy.db", db_path / "trivy.db", db["database_sha256"])
    extract_member(database_archive, "metadata.json", db_path / "metadata.json", db["metadata_sha256"])
    (root / "trivy.sha256").write_text(trivy["binary_sha256"] + "\n")
    (root / "db.sha256").write_text(db["database_sha256"] + "\n")
    (root / "image-lock.json").write_text(json.dumps({
        "bases": {key: item["ref"] for key, item in lock["bases"].items()},
        "files": {key: {"url": item["url"], "sha256": item["sha256"]} for key, item in lock["files"].items()},
    }, sort_keys=True) + "\n")


if __name__ == "__main__":
    try:
        stage(json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2]))
    except (OSError, ValueError, KeyError, tarfile.TarError, TypeError) as error:
        # Requests can include a CDN-signed URL. Keep the error sanitized.
        print(f"Vela reviewed-input staging failed ({type(error).__name__})", file=sys.stderr)
        raise SystemExit(1)
