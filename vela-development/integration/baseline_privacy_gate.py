#!/usr/bin/env python3
"""Development-only privacy regression check for smgsp6/3x-ui vela-dev.

Baseline false positives remain unresolved and MUST be reviewed before
production release. A successful result proves only that the candidate
adds no scanner-detectable finding relative to the pinned upstream baseline.
"""
from pathlib import Path
import subprocess
import sys

BASE = "5297fd3c8495d80fab97ae511553fa545c69e913"
EXACT_UPSTREAM_FIXTURES = {
    "frontend/src/pages/xray/outbounds/transport/masque.tsx": "e0416fb751a163f034f2464ae6d181bca6bea5dc",
    "frontend/src/test/warp-masque-modal.test.tsx": "d440d4e7dc4293ec5e1f8b975724d2b129d61df7",
    "internal/web/runtime/remote_test.go": "5fee05759d00010c00435a7a58814472b199798d",
    "internal/web/service/setting_mtls_bundle_test.go": "3526725dbfff5b21fbee5c4ec2664a67bf938328",
}

# Exact blob from the historical image-audit test. The markers were followed
# by literal synthetic placeholders, with no complete key material.
EXACT_VELA_HISTORICAL_FIXTURES = {
    "BLOCK: 83627b0ffc78c9cbeacac7f7a37c06ca6ac61cbd: historical private key block",
}

def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()

def findings(script, repo, *args):
    result = subprocess.run([sys.executable, script, str(repo), *args], capture_output=True, text=True)
    blocks = sorted(x for x in (result.stdout + result.stderr).splitlines() if x.startswith("BLOCK: "))
    if result.returncode not in (0, 1) or (result.returncode and not blocks):
        raise RuntimeError("scanner failed to complete safely: " + script)
    return blocks

def audit():
    origin = git("remote", "get-url", "origin")
    if origin not in ("https://github.com/smgsp6/3x-ui", "https://github.com/smgsp6/3x-ui.git"):
        raise RuntimeError("unexpected remote")
    if git("branch", "--show-current") != "vela-dev":
        raise RuntimeError("wrong branch")
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], check=True)
    for path, sha in EXACT_UPSTREAM_FIXTURES.items():
        if git("rev-parse", f"{BASE}:{path}") != sha or git("hash-object", path) != sha:
            raise RuntimeError("known fixture modified: " + path)
    source = findings("deploy/vela/privacy_audit.py", Path("."))
    expected = sorted("BLOCK: " + path + ": private key block" for path in EXACT_UPSTREAM_FIXTURES)
    if source != expected:
        raise RuntimeError("new or different private-content source finding")
    script = "deploy/vela/git_history_audit.py"
    baseline = set(findings(script, Path("."), "--ref", BASE))
    candidate = set(findings(script, Path("."), "--ref", "HEAD"))
    if candidate - baseline - EXACT_VELA_HISTORICAL_FIXTURES:
        raise RuntimeError("new historical private-content finding")
    print(f"PASS (development only): zero unreviewed historical findings; "
          f"{len(candidate & baseline)} inherited and "
          f"{len(candidate & EXACT_VELA_HISTORICAL_FIXTURES)} pinned synthetic matches")
    print("WARNING: inherited historical findings still block a production release")

if __name__ == "__main__":
    try:
        audit()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Vela privacy regression gate BLOCKED: {error}", file=sys.stderr)
        sys.exit(1)
