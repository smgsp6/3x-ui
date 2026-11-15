#!/usr/bin/env python3
"""Fail-closed pre-release privacy review for smgsp6/3x-ui (Vela).

No network access. Never prints matched credential content. This checks the
current checkout and obvious build-context leaks; it DOES NOT replace scanning
Git history, Docker layers, CI logs, or dependency/supply-chain auditing.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# Only high-confidence signatures. Deliberately avoid scanning generic
# 'password=' examples that are common in upstream documentation/tests.
SECRET_SIGNATURES = {
    "private key block": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "Telegram bot token": re.compile(rb"(?<![A-Za-z0-9])\d{7,12}:[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])"),
    "GitHub classic token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{36}(?![A-Za-z0-9])"),
    "GitHub fine-grained token": re.compile(rb"github_pat_[A-Za-z0-9_]{50,}(?![A-Za-z0-9_])"),
    "AWS access key": re.compile(rb"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"),
    "Stripe live secret": re.compile(rb"sk_live_[A-Za-z0-9]{20,}(?![A-Za-z0-9])"),
}

PRIVATE_ROOTS = {
    "secrets", ".secrets", "db", "cert", "acme", "pgdata",
    "backup", "backups", "failed-updates", "private-data",
}
PRIVATE_FILENAMES = {"id_rsa", "id_ed25519", "credentials.json", "token.txt"}
PRIVATE_SUFFIXES = {".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3", ".dump"}
SAFE_PUBLIC_PEMS = {"internal/pia/trust/serverlist_public_key.pem"}
SKIP_SCAN_DIRS = {".git", "node_modules", "dist", "build", ".cache", ".venv", "venv", ".next", "__pycache__", ".pytest_cache"}

# Explicit ignore guards for upstream `Dockerfile: COPY . .`. No clever
# approximation of the complete Docker .dockerignore syntax is attempted.
# We instead demand exact, reviewable rules for each sensitive family.
REQUIRED_DOCKER_IGNORES = {
    ".env", ".env.*", "**/.env", "**/.env.*",
    "secrets/", "**/secrets/", "acme/", "**/acme/",
    "db", "cert", "backups/", "failed-updates/",
    "*.key", "*.p12", "*.pfx", "**/*private*.pem", "**/__pycache__/", "*.pyc",
}


def risky_name(relative: str) -> bool:
    path = Path(relative)
    parts = [x.lower() for x in path.parts]
    name = path.name.lower()
    if not parts:
        return False
    if parts[0] in PRIVATE_ROOTS:
        return True
    if name in PRIVATE_FILENAMES or name.endswith(tuple(PRIVATE_SUFFIXES)):
        return True
    if name == ".env" or name.startswith(".env."):
        return name not in (".env.example", ".env.sample", ".env.template")
    if name.endswith(".pem") and relative not in SAFE_PUBLIC_PEMS and "private" in name:
        return True
    # Actual ACME and credential folders may be nested within a source tree.
    if any(p in {"secrets", ".secrets", "acme", "backups", "failed-updates"} for p in parts[:-1]):
        return True
    return False


def git_paths(repo: Path) -> list[str]:
    proc = subprocess.run(["git", "ls-files", "-z", "--cached"], cwd=repo,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return [os.fsdecode(raw) for raw in proc.stdout.split(b"\0") if raw]


def inspect_bytes(path: Path) -> list[str]:
    # Avoid reading large user databases and binary builds into memory.
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
            return []
        body = path.read_bytes()
    except OSError:
        return ["unreadable file"]
    return [label for label, pattern in SECRET_SIGNATURES.items() if pattern.search(body)]


def check_dockerignore(repo: Path) -> list[str]:
    config = repo / ".dockerignore"
    try:
        lines = config.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ["missing Docker ignore rules"]
    declared = {line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")}
    missing = sorted(REQUIRED_DOCKER_IGNORES - declared)
    warnings = [f"missing required .dockerignore rule: {item}" for item in missing]
    # Later negations of protected paths are a release blocker: the
    # conservative review cannot prove the resulting context is private.
    # Even `!*` can silently re-include .env or keys. Until the complete Docker
    # pattern semantics are reviewed, ANY re-include fails closed.
    for line in declared:
        if line.startswith("!"):
            warnings.append(".dockerignore contains a risky re-include rule")
    return warnings


def audit(repo: Path) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    try:
        tracked = git_paths(repo)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return [("repository", "not a readable Git checkout")]

    for rel in tracked:
        if risky_name(rel):
            findings.append((rel, "sensitive filename committed to Git"))
        path = repo / rel
        # Scan all tracked files, including tests and documentation: a secret
        # copied to a test fixture is still exposed if this repository is public.
        for issue in inspect_bytes(path):
            findings.append((rel, issue))

    for issue in check_dockerignore(repo):
        findings.append((".dockerignore", issue))

    # Detect untracked/ignored sensitive content within likely Docker COPY
    # roots. This intentionally errs on the safe side: some files may be
    # ignored, but a human must check Docker's real context before releasing.
    tracked_set = set(tracked)
    for root, dirs, files in os.walk(repo, followlinks=False):
        rootpath = Path(root)
        # Root runtime state is intentionally excluded by .dockerignore. Do not
        # read user secrets merely to scan them: verify the exclusion guards.
        if rootpath == repo:
            dirs[:] = [d for d in dirs if d not in SKIP_SCAN_DIRS and d.lower() not in PRIVATE_ROOTS
                       and not Path(root, d).is_symlink()]
        else:
            dirs[:] = [d for d in dirs if d not in SKIP_SCAN_DIRS and not Path(root, d).is_symlink()]
        for filename in files:
            path = rootpath / filename
            rel = path.relative_to(repo).as_posix()
            if rel in tracked_set:
                continue
            # Explicitly ignored private root files (e.g. .env and *.key at
            # repository root) need a separate Docker build-context review.
            if path.parent == repo and risky_name(rel) and filename.startswith('.env'):
                continue
            if path.is_symlink():
                findings.append((rel, "untracked symlink in Docker source path"))
                continue
            if risky_name(rel):
                findings.append((rel, "untracked sensitive filename in Docker source path"))
                continue
            for issue in inspect_bytes(path):
                findings.append((rel, "untracked potential Docker context leak: " + issue))
    return sorted(set(findings))


def main() -> int:
    if len(sys.argv) > 2:
        print("Usage: privacy_audit.py [repo_dir]", file=sys.stderr)
        return 2
    repo = Path(sys.argv[1] if len(sys.argv) == 2 else ".").resolve()
    findings = audit(repo)
    for path, issue in findings:
        # Never print credentials or file contents, only relative paths and labels.
        print(f"BLOCK: {path}: {issue}", file=sys.stderr)
    if findings:
        print(f"BLOCKED: {len(findings)} privacy-related findings; manual release review required.", file=sys.stderr)
        return 1
    print("PASS: 当前源码与保守 Docker 构建目录隐私检查未发现预设问题；不代表全量审计完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
