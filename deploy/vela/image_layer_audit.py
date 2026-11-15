#!/usr/bin/env python3
"""Offline, bounded-memory safety gate for a `docker image save` tar stream.

Usage: docker image save image:tag | python3 image_layer_audit.py --stdin

Checks *all final-image layers*, including files deleted by later layers. The
report never prints file contents, file names, environment values or secrets.
This is one safety gate, not a substitute for scanning builder-stage caches,
the Docker build context, the Git history, or third-party base images.
"""
import argparse
import io
import re
import sys
import tarfile

# Exact private-file categories. A public PEM certificate is not a secret;
# private-key headers are detected separately by content.
PRIVATE_BASENAMES = {'.env', 'x-ui.db', 'vela_bot_token', 'credentials.json', 'id_rsa', 'id_ed25519'}
PRIVATE_DIRS = {'secrets', '.secrets', 'backups', 'failed-updates', '.acme.sh'}
PRIVATE_EXTENSIONS = ('.db', '.sqlite', '.sqlite3', '.dump', '.p12', '.pfx', '.key')
KEY_HEADER = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----')
TELEGRAM_TOKEN = re.compile(rb'\b\d{6,13}:[A-Za-z0-9_-]{32,}\b')
AWS_KEY = re.compile(rb'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b')
# Keep stream parsing bounded; large files are scanned incrementally.
CHUNK = 64 * 1024


def private_path(name):
    parts = [p for p in name.replace('\\', '/').split('/') if p not in ('', '.')]
    if not parts:
        return False
    normalized = [x.lower() for x in parts]
    base = normalized[-1]
    return (base in PRIVATE_BASENAMES or base.startswith('.env.')
            or any(x in PRIVATE_DIRS for x in normalized[:-1])
            or base.endswith(PRIVATE_EXTENSIONS))


def file_has_secret(f):
    overlap = b''
    while True:
        chunk = f.read(CHUNK)
        if not chunk:
            return False
        current = overlap + chunk
        if KEY_HEADER.search(current) or TELEGRAM_TOKEN.search(current) or AWS_KEY.search(current):
            return True
        overlap = current[-256:]


def audit_image_save(fileobj):
    layer_count = 0
    checked = 0
    violations = 0
    try:
        # `r|*` supports Docker's streaming tar without writing the image to disk.
        with tarfile.open(fileobj=fileobj, mode='r|*') as image:
            for outer in image:
                if not outer.isfile():
                    continue
                # Docker-save config JSON contains image environment variables;
                # do not echo any values if the scan detects a credential.
                if outer.name.endswith('.json') and '/' not in outer.name:
                    stream = image.extractfile(outer)
                    if stream is not None:
                        checked += 1
                        if file_has_secret(stream):
                            violations += 1
                    continue
                if not outer.name.endswith('/layer.tar') and outer.name != 'layer.tar':
                    continue
                layer_count += 1
                source = image.extractfile(outer)
                if source is None:
                    raise ValueError('unreadable image layer')
                with tarfile.open(fileobj=source, mode='r|*') as layer:
                    for member in layer:
                        if member.isfile():
                            checked += 1
                            if private_path(member.name):
                                violations += 1
                            stream = layer.extractfile(member)
                            if stream is None:
                                raise ValueError('unreadable layer member')
                            if file_has_secret(stream):
                                violations += 1
                        elif member.issym() or member.islnk():
                            # This gate only detects private data, not unsafe
                            # runtime link-following; that is a separate check.
                            continue
    except (tarfile.TarError, OSError, EOFError, ValueError) as exc:
        raise ValueError('cannot audit Docker image; archive is invalid') from exc
    if layer_count == 0:
        raise ValueError('Docker image has no readable layer archives')
    return layer_count, checked, violations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stdin', action='store_true', help='read docker image save tar from standard input')
    args = parser.parse_args()
    if not args.stdin:
        parser.error('use --stdin; this tool never contacts Docker or the network')
    try:
        layers, checked, risks = audit_image_save(sys.stdin.buffer)
    except ValueError:
        print('Vela image audit: archive invalid or unreadable (fail closed)', file=sys.stderr)
        return 2
    if risks:
        print(f'Vela image audit: FAIL ({risks} potential private-data findings, contents/names suppressed)', file=sys.stderr)
        return 1
    print(f'Vela image audit: PASS ({layers} image layer(s), {checked} file(s) scanned)')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
