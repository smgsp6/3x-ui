#!/usr/bin/env python3
"""Classify PEM fixture ownership in a disposable PUBLIC Alpine package image.

Prints only package identifiers and bounded counts. Never prints or stores
file paths, file contents, key fingerprints, private data, or parser errors.
This is a diagnostic, not a production authorization or secret waiver.
"""
import collections
import os
import re
import subprocess
from pathlib import Path

HEADER = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")
PACKAGE = re.compile(rb"is owned by ([A-Za-z0-9_.+~:-]{1,100})")
ROOTS = ["/etc", "/usr", "/lib", "/bin", "/sbin"]
COUNTS = collections.Counter()
EXAMINED = 0
for root in ROOTS:
    if not os.path.isdir(root):
        continue
    for directory, subdirs, filenames in os.walk(root, followlinks=False):
        subdirs[:] = [d for d in subdirs if not os.path.islink(os.path.join(directory, d))]
        for filename in filenames:
            path = Path(directory) / filename
            try:
                st = path.lstat()
                if not path.is_file() or path.is_symlink() or st.st_size > 32 * 1024 * 1024:
                    continue
                EXAMINED += 1
                data = path.read_bytes()
                matches = list(HEADER.finditer(data))
                if not matches:
                    continue
                result = subprocess.run(["apk", "info", "-W", str(path)],
                                        capture_output=True, timeout=8, check=False)
                owners = PACKAGE.findall(result.stdout)
                owner = owners[0].decode("ascii") if owners else "unattributed"
                for match in matches:
                    footer = match.group().replace(b"BEGIN", b"END", 1)
                    end = data.find(footer, match.end(), match.end() + 128 * 1024)
                    if end < 0:
                        classification = "header_only"
                    else:
                        candidate = data[match.start():end + len(footer)]
                        parsed = subprocess.run(
                            ["openssl", "pkey", "-inform", "PEM", "-noout"],
                            input=candidate, capture_output=True, timeout=5, check=False)
                        classification = "parseable" if parsed.returncode == 0 else "unparseable"
                    COUNTS[(owner, classification)] += 1
                if sum(COUNTS.values()) > 32:
                    raise RuntimeError("unexpected number of PEM markers")
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                # Never surface exceptions that might contain private file paths.
                raise SystemExit("Public-package provenance diagnostic could not complete") from None
print("PUBLIC_RUNTIME_FILES_CHECKED", EXAMINED)
print("PUBLIC_RUNTIME_PEM_HITS", sum(COUNTS.values()))
for (owner, classification), count in sorted(COUNTS.items()):
    # Owner is a public package ID extracted from apk, not a pathname.
    print(f"PUBLIC_PACKAGE {owner}: {classification}={count}")
