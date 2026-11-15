#!/usr/bin/env python3
"""Local historic Git blob audit; never prints or uploads secret values.

This scans all reachable objects in the locally available Git refs, including
secret material removed from the current checkout. It is NOT proof that data
was never exposed: deleted refs, shallow history and external artifacts need
independent review.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from privacy_audit import SECRET_SIGNATURES, risky_name

MAX_BLOB_BYTES = 8 * 1024 * 1024
MAX_OBJECTS = 150000


def _read_exact(stream, count: int) -> bytes:
    chunks = []
    while count:
        data = stream.read(min(count, 65536))
        if not data:
            raise ValueError('truncated Git object stream')
        chunks.append(data)
        count -= len(data)
    return b''.join(chunks)


def _discard(stream, count: int) -> None:
    while count:
        data = stream.read(min(count, 65536))
        if not data:
            raise ValueError('truncated Git object stream')
        count -= len(data)


def audit_history(repo: Path) -> tuple[list[str], int]:
    listing = subprocess.run(['git', 'rev-list', '--objects', '--all'], cwd=repo,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    refs = []
    for row in listing.stdout.splitlines():
        raw_oid, _, raw_path = row.partition(b' ')
        oid = raw_oid.decode('ascii')
        if len(oid) not in (40, 64) or any(c not in '0123456789abcdef' for c in oid):
            raise ValueError('invalid Git object ID in history')
        path = raw_path.decode('utf-8', errors='replace')
        refs.append((oid, path))
    if len(refs) > MAX_OBJECTS:
        raise ValueError('history exceeds review limits; run a dedicated complete review')
    if not refs:
        return [], 0

    seen = set()
    findings = []
    proc = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=repo,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, bufsize=0)
    try:
        assert proc.stdin is not None and proc.stdout is not None
        for oid, path in refs:
            proc.stdin.write((oid + '\n').encode('ascii'))
            header = proc.stdout.readline()
            fields = header.decode('ascii', errors='replace').split()
            if len(fields) != 3 or fields[0] != oid or not fields[2].isdigit():
                raise ValueError('invalid Git object header or missing object')
            size = int(fields[2])
            typ = fields[1]
            if typ == 'blob' and path and risky_name(path):
                seen.add((oid, 'historical sensitive filename'))
            if typ == 'blob' and size > MAX_BLOB_BYTES:
                # A skipped oversized object is an incomplete security audit.
                seen.add((oid, 'oversized historic blob requires manual review'))
                _discard(proc.stdout, size)
            elif typ == 'blob':
                body = _read_exact(proc.stdout, size)
                for label, signature in SECRET_SIGNATURES.items():
                    if signature.search(body):
                        seen.add((oid, 'historical ' + label))
            else:
                _discard(proc.stdout, size)
            if proc.stdout.read(1) != b'\n':
                raise ValueError('invalid Git batch delimiter')
        for oid, label in sorted(seen):
            # IDs are non-secret object hashes; never display matched bytes.
            findings.append(f'{oid[:12]}: {label}')
    finally:
        if proc.stdin:
            proc.stdin.close()
        if proc.stdout:
            proc.stdout.close()
        proc.terminate()
        proc.wait(timeout=5)
    return findings, len(refs)


def main() -> int:
    if len(sys.argv) > 2:
        print('Usage: git_history_audit.py [repo_dir]', file=sys.stderr)
        return 2
    repo = Path(sys.argv[1] if len(sys.argv) == 2 else '.').resolve()
    try:
        shallow = subprocess.run(['git', 'rev-parse', '--is-shallow-repository'], cwd=repo,
                                 capture_output=True, text=True, check=True).stdout.strip()
        if shallow != 'false':
            raise ValueError('shallow Git checkout; historical scan cannot be considered complete')
        findings, count = audit_history(repo)
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(f'BLOCKED: cannot complete historic Git object audit: {error}', file=sys.stderr)
        return 1
    for item in findings:
        print('BLOCK: ' + item, file=sys.stderr)
    if findings:
        print(f'BLOCKED: {len(findings)} historic findings in {count} objects', file=sys.stderr)
        return 1
    print(f'PASS: {count} reachable Git objects scanned; unreachable history and external logs remain unverified.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
