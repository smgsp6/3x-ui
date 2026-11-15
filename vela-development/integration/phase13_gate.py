#!/usr/bin/env python3
"""Vela phase-13 offline release gate: inspect an archived preview before Git integration.

No network calls, no GitHub credentials, no live server access. This is NOT a
production-release security audit.
"""
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile

EXPECTED_ZIP_SHA256 = "3d0c33a8c7d046a4f00527687eec64efe179f8a3ede957de05d0ea57395de0fd"
EXPECTED_BLOB_SIZE = 1271482
FORBIDDEN_SUFFIXES = (".pem", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db", ".key", ".log", ".bak", ".sql")
FORBIDDEN_DIRS = {"secrets", "backups", "acme", "pgdata", "node_modules", ".git", "__pycache__", "failed-updates"}
ALLOWED_ROOTS = {"internal", "frontend", "deploy", "tests", "brand", "docs"}
ALLOWED_FILES = {".gitignore", ".dockerignore", "README.md", "apply_to_repo.py", "SHA256SUMS"}
HIGH_CONFIDENCE_SECRETS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    re.compile(rb"(?<![A-Za-z0-9_])(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{70,}"),
    re.compile(rb"(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])"),
    re.compile(rb"(?<![0-9])\d{8,12}:[A-Za-z0-9_-]{35,}(?![A-Za-z0-9_-])"),
)

def fail(reason):
    raise SystemExit("Vela source integration blocked: " + reason)

def validate_path(name):
    if not name or "\\" in name or name.startswith("/") or "//" in name:
        fail("unsafe archive pathname")
    path = PurePosixPath(name)
    if any(part in ("", ".", "..") or ":" in part for part in path.parts):
        fail("unsafe path component")
    parts = path.parts
    if any(part.lower() in FORBIDDEN_DIRS for part in parts[:-1]):
        fail("runtime-data directory in package")
    base = parts[-1].lower()
    if base == ".env" or (base.startswith(".env.") and not base.endswith(".example")):
        fail("real environment file in package")
    if base.endswith(FORBIDDEN_SUFFIXES) or base.startswith("id_rsa"):
        fail("potential private runtime file in package")
    if len(parts) > 20 or len(name) > 300:
        fail("excessive archive path")
    return path

def scan_bytes(data):
    for pat in HIGH_CONFIDENCE_SECRETS:
        if pat.search(data):
            fail("high-confidence credential / private-key signature in source")
    if b"\x00" in data[:4096] and len(data) < 2048:
        return

def archive_gate(zip_path, dest):
    if zip_path.stat().st_size != EXPECTED_BLOB_SIZE:
        fail("archive length differs from pinned GitHub artifact")
    if hashlib.sha256(zip_path.read_bytes()).hexdigest() != EXPECTED_ZIP_SHA256:
        fail("archive SHA256 differs from pinned phase-12 artifact")
    if dest.exists() and any(dest.iterdir()):
        fail("destination directory must be empty")
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        infos = archive.infolist()
        if not infos or len(infos) > 512:
            fail("archive entry limit")
        all_names = [x.filename for x in infos if not x.is_dir()]
        if "apply_to_repo.py" in all_names:
            prefix = ""
        else:
            prefixes = {x.split("/", 1)[0] for x in all_names}
            if len(prefixes) != 1:
                fail("unknown archive directory layout")
            prefix = next(iter(prefixes)) + "/"
            if prefix + "apply_to_repo.py" not in all_names:
                fail("missing patch entrypoint")
        seen = set()
        files = {}
        total = 0
        for entry in infos:
            original = entry.filename
            if prefix and not original.startswith(prefix):
                fail("archive entry outside package root")
            name = original[len(prefix):]
            if not name:
                continue
            if entry.is_dir():
                continue
            path = validate_path(name)
            lower = path.as_posix().casefold()
            if lower in seen:
                fail("duplicate or ambiguous archive name")
            seen.add(lower)
            mode = (entry.external_attr >> 16) & 0o170000
            if mode not in (0, stat.S_IFREG):
                fail("special file or symlink in archive")
            if entry.file_size > 6 * 1024 * 1024:
                fail("oversized package entry")
            total += entry.file_size
            if total > 40 * 1024 * 1024:
                fail("archive inflated size limit")
            data = archive.read(entry)
            scan_bytes(data)
            files[path.as_posix()] = (data, entry.external_attr >> 16)
        if "SHA256SUMS" not in files or "apply_to_repo.py" not in files:
            fail("archive lacks manifest or patch script")
        hashes = {}
        for line in files["SHA256SUMS"][0].decode("utf-8").splitlines():
            digest, sep, name = line.partition("  ")
            if sep != "  " or not re.fullmatch("[a-f0-9]{64}", digest):
                fail("malformed SHA256SUMS")
            path = validate_path(name).as_posix()
            if path in hashes:
                fail("duplicate manifest pathname")
            hashes[path] = digest
        if set(hashes) != set(files) - {"SHA256SUMS"}:
            fail("manifest does not exactly enumerate archive content")
        for name, digest in hashes.items():
            if hashlib.sha256(files[name][0]).hexdigest() != digest:
                fail("member digest differs from manifest")
        for name, (data, mode) in files.items():
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
            target.chmod(0o755 if mode & 0o111 and (name.endswith((".sh", ".py")) or name == "deploy/vela/vela") else 0o644)
    print(f"Archive gate passed: {len(files)} verified files, pinned SHA256, no special entries")

def git_output(*args):
    return subprocess.check_output(["git", *args])

def audit_git_index():
    deleted = git_output("diff", "--cached", "--diff-filter=D", "--name-only", "-z")
    if deleted:
        fail("upstream file deletion detected")
    paths = [p.decode("utf-8") for p in git_output("diff", "--cached", "--name-only", "-z").split(b"\x00") if p]
    if len(paths) < 25 or len(paths) > 300:
        fail("unexpected integration change count")
    if git_output("show", "HEAD:go.mod").decode("utf-8").splitlines()[0] != "module github.com/mhsanaei/3x-ui/v3":
        fail("upstream module path unexpectedly differs")
    for name in paths:
        path = validate_path(name)
        p = path.as_posix()
        if p not in ALLOWED_FILES and path.parts[0] not in ALLOWED_ROOTS and p != ".github/workflows/vela-pr-check.yml":
            fail("modification outside the approved source tree")
        if p == "go.mod":
            fail("Go module modification not reviewed")
        target = Path(p)
        if target.is_symlink():
            fail("new or changed symlink")
        if target.is_file():
            scan_bytes(target.read_bytes())
            if p.endswith(".yml") and p.startswith(".github/workflows/"):
                s = target.read_text("utf-8")
                if any(re.search(x, s, re.I | re.M) for x in (
                    r"^\s*pull_request_target\s*:",
                    r"^\s*workflow_run\s*:",
                    r"\bsecrets\s*\.",
                    r"contents\s*:\s*write",
                )):
                    fail("unreviewed elevated CI permissions in package workflow")
    if git_output("show", ":go.mod").decode("utf-8").splitlines()[0] != "module github.com/mhsanaei/3x-ui/v3":
        fail("Go module identity altered")
    subprocess.run(["git", "diff", "--cached", "--check"], check=True)
    print(f"Git integration gate passed: {len(paths)} scoped changes; no deletions or evident credentials")

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    arch = sub.add_parser("verify-archive")
    arch.add_argument("zip", type=Path)
    arch.add_argument("dest", type=Path)
    sub.add_parser("audit-index")
    args = parser.parse_args()
    if args.cmd == "verify-archive":
        archive_gate(args.zip, args.dest)
    else:
        audit_git_index()

if __name__ == "__main__":
    main()
