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


def classify_image_path(name):
    """Return only a fixed bucket, never report the image member pathname."""
    name = name.replace('\\\\', '/').lstrip('./')
    if name == 'app/x-ui':
        return 'vela_panel_binary'
    if name.startswith('app/bin/xray-linux-'):
        return 'xray_binary'
    if name.startswith('app/bin/mtg-linux-'):
        return 'mtg_binary'
    if name.startswith(('usr/', 'lib/', 'etc/', 'bin/', 'sbin/')):
        return 'os_content'
    return 'other_content'


def pem_footer_diagnostic(current, match, stream, diagnostics):
    """Bounded, in-memory evidence check; NEVER reads/logs any key body.

    Header alone is not enough to prove a private key was embedded, but both
    header-only and complete candidates remain release-blocking.
    """
    footer = match.group(0).replace(b'BEGIN', b'END', 1)
    limit = 128 * 1024
    tail = bytearray(current[match.end():match.end() + limit])
    while footer not in tail and len(tail) < limit:
        chunk = stream.read(min(CHUNK, limit - len(tail)))
        if not chunk:
            break
        tail.extend(chunk)
    label = 'pem_header_with_footer' if footer in tail else 'pem_header_no_footer_within_bound'
    diagnostics[label] = diagnostics.get(label, 0) + 1


def file_has_secret(f, diagnostics=None):
    """Return a boolean; optional diagnosis contains counts only, never bytes."""
    overlap = b''
    first = True
    is_elf = False
    while True:
        chunk = f.read(CHUNK)
        if not chunk:
            return False
        if first:
            is_elf = chunk.startswith(b'\x7fELF')
            first = False
        current = overlap + chunk
        matched = None
        pem_match = KEY_HEADER.search(current)
        if pem_match:
            matched = 'pem'
            if diagnostics is not None:
                pem_footer_diagnostic(current, pem_match, f, diagnostics)
        elif TELEGRAM_TOKEN.search(current):
            matched = 'telegram'
        elif AWS_KEY.search(current):
            matched = 'aws'
        if matched:
            if diagnostics is not None:
                category = matched + ('_elf' if is_elf else '_nonelf')
                diagnostics[category] = diagnostics.get(category, 0) + 1
            return True
        overlap = current[-256:]


def scan_layer_tar(source, diagnostics=None):
    """Inspect a layer regardless of whether its outer name is legacy or OCI."""
    checked = violations = 0
    with tarfile.open(fileobj=source, mode='r|*') as layer:
        for member in layer:
            if member.isfile():
                checked += 1
                if private_path(member.name):
                    violations += 1
                    if diagnostics is not None:
                        diagnostics['private_path'] = diagnostics.get('private_path', 0) + 1
                stream = layer.extractfile(member)
                if stream is None:
                    raise ValueError('unreadable layer member')
                if file_has_secret(stream, diagnostics):
                    violations += 1
                    if diagnostics is not None:
                        diagnostics['layer_content'] = diagnostics.get('layer_content', 0) + 1
                        bucket = 'source_' + classify_image_path(member.name)
                        diagnostics[bucket] = diagnostics.get(bucket, 0) + 1
            elif member.issym() or member.islnk():
                # No link is followed or dereferenced. Runtime link-policy
                # validation is intentionally separate from this privacy gate.
                continue
    return checked, violations


def scan_oci_json(source):
    """Parse small OCI config/index/manifest documents; never print their values."""
    import json
    # OCI descriptors should be small. Refuse a huge or malformed JSON blob
    # rather than assuming it is harmless metadata.
    blob = source.read((2 << 20) + 1)
    if len(blob) > (2 << 20):
        raise ValueError('oversized OCI metadata')
    try:
        obj = json.loads(blob)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError('invalid OCI metadata') from exc
    if not isinstance(obj, (dict, list)):
        raise ValueError('invalid OCI metadata shape')
    return int(file_has_secret(io.BytesIO(blob)))


OCI_BLOB = re.compile(r'^blobs/sha256/[a-f0-9]{64}$')


def audit_image_save(fileobj, diagnostics=None):
    layer_count = 0
    checked = 0
    violations = 0
    seen_oci = False
    seen_legacy = False
    try:
        # Docker Engines using the containerd image store can export OCI-style
        # blobs/sha256/<digest> instead of legacy <id>/layer.tar paths.
        # Scan every blob, including ones not referenced by the final manifest:
        # deleting a secret in a later layer must not erase the finding.
        with tarfile.open(fileobj=fileobj, mode='r|*') as image:
            for outer in image:
                if not outer.isfile():
                    continue
                name = outer.name
                source = image.extractfile(outer)
                if source is None:
                    raise ValueError('unreadable archive member')

                if name == 'layer.tar' or name.endswith('/layer.tar'):
                    seen_legacy = True
                    layer_count += 1
                    count, risks = scan_layer_tar(source, diagnostics)
                    checked += count
                    violations += risks
                    continue

                if name.startswith('blobs/'):
                    seen_oci = True
                    if OCI_BLOB.fullmatch(name) is None:
                        raise ValueError('unrecognized OCI blob path')
                    # OCI blobs contain either JSON configs/manifests or
                    # (possibly compressed) tar layers. Peeking preserves the
                    # stream for the following bounded parse.
                    prefix = source.peek(256).lstrip()
                    if prefix.startswith((b'{', b'[')):
                        checked += 1
                        risk = scan_oci_json(source)
                        violations += risk
                        if risk and diagnostics is not None:
                            diagnostics['metadata_content'] = diagnostics.get('metadata_content', 0) + 1
                    else:
                        layer_count += 1
                        count, risks = scan_layer_tar(source, diagnostics)
                        checked += count
                        violations += risks
                    continue

                # Docker legacy manifest/config, OCI index, oci-layout and
                # other top-level metadata are still scanned for credentials.
                checked += 1
                if file_has_secret(source):
                    violations += 1
                    if diagnostics is not None:
                        diagnostics['metadata_content'] = diagnostics.get('metadata_content', 0) + 1
    except (tarfile.TarError, OSError, EOFError, ValueError) as exc:
        raise ValueError('cannot audit Docker image; archive is invalid') from exc
    if layer_count == 0 or (seen_oci and seen_legacy):
        raise ValueError('image has no layers or ambiguous archive layout')
    return layer_count, checked, violations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stdin', action='store_true', help='read docker image save tar from standard input')
    parser.add_argument('--diagnostic-counts', action='store_true',
                        help='print aggregate finding categories only; never paths or contents')
    args = parser.parse_args()
    if not args.stdin:
        parser.error('use --stdin; this tool never contacts Docker or the network')
    diagnostics = {} if args.diagnostic_counts else None
    try:
        layers, checked, risks = audit_image_save(sys.stdin.buffer, diagnostics)
    except ValueError:
        print('Vela image audit: archive invalid or unreadable (fail closed)', file=sys.stderr)
        return 2
    if risks:
        print(f'Vela image audit: FAIL ({risks} potential private-data findings, contents/names suppressed)', file=sys.stderr)
        if diagnostics is not None:
            print('Aggregate categories (no paths, values or contents): '
                  + ', '.join(f'{kind}={diagnostics.get(kind, 0)}'
                              for kind in ('private_path', 'layer_content', 'metadata_content')),
                  file=sys.stderr)
        if diagnostics is not None:
            print('Signature classes (counts only): '
                  + ', '.join(f'{kind}={diagnostics.get(kind, 0)}'
                              for kind in ('pem_elf', 'pem_nonelf',
                                           'telegram_elf', 'telegram_nonelf',
                                           'aws_elf', 'aws_nonelf')),
                  file=sys.stderr)
            print('Bounded PEM header/footer review (counts only): '
                  + ', '.join(f'{kind}={diagnostics.get(kind, 0)}'
                              for kind in ('pem_header_with_footer',
                                           'pem_header_no_footer_within_bound')),
                  file=sys.stderr)
            print('Image component buckets (counts only): '
                  + ', '.join(f'{kind}={diagnostics.get(kind, 0)}'
                              for kind in ('source_vela_panel_binary', 'source_xray_binary',
                                           'source_mtg_binary', 'source_os_content',
                                           'source_other_content')),
                  file=sys.stderr)
        return 1
    print(f'Vela image audit: PASS ({layers} image layer(s), {checked} file(s) scanned)')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
