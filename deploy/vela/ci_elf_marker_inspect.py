#!/usr/bin/env python3
"""Read-only ELF marker inventory. NOT a private-key clearance or release waiver.

Examines only a disposable CI-built binary. Reports fixed section categories
and counts; never logs offsets, pathnames, strings, binary bytes, or secrets.
"""
import argparse
from collections import Counter
from pathlib import Path
import re
import struct

HEADER = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")
MAX_BINARY = 256 * 1024 * 1024
MAX_SECTIONS = 4096

def sections(data):
    if len(data) < 64 or data[:4] != b"\x7fELF" or data[4] not in (1, 2) or data[5] not in (1, 2):
        raise ValueError("not a supported ELF binary")
    endian = "<" if data[5] == 1 else ">"
    if data[4] == 2:
        shoff = struct.unpack_from(endian + "Q", data, 40)[0]
        entsize, count, stridx = struct.unpack_from(endian + "HHH", data, 58)
        fmt = endian + "IIQQQQIIQQ"
    else:
        shoff = struct.unpack_from(endian + "I", data, 32)[0]
        entsize, count, stridx = struct.unpack_from(endian + "HHH", data, 46)
        fmt = endian + "IIIIIIIIII"
    if (not 0 < count <= MAX_SECTIONS or not 0 < entsize <= 256
            or entsize < struct.calcsize(fmt) or stridx >= count
            or shoff + entsize * count > len(data)):
        raise ValueError("invalid ELF section table")
    entries = [struct.unpack_from(fmt, data, shoff + i * entsize) for i in range(count)]
    # sh_offset and sh_size occupy positions 4 and 5 for both ELF classes.
    strtab = entries[stridx]
    start, size = strtab[4], strtab[5]
    if start + size > len(data):
        raise ValueError("invalid ELF section names")
    names = data[start:start + size]
    out = []
    for entry in entries:
        nameid, offset, size = entry[0], entry[4], entry[5]
        if offset + size > len(data) or nameid >= len(names):
            raise ValueError("invalid ELF section bounds")
        name = names[nameid:names.find(b"\0", nameid) if b"\0" in names[nameid:] else len(names)]
        # An empty or unusual section label must remain a separate unknown class.
        if name == b".rodata":
            label = "readonly_constants"
        elif name in (b".data", b".bss", b".noptrdata", b".data.rel.ro"):
            label = "writable_data"
        elif name == b".text":
            label = "machine_code"
        else:
            label = "other_or_unknown"
        out.append((offset, offset + size, label))
    return out

def classify(data):
    counts = Counter()
    parts = sections(data)
    for hit in HEADER.finditer(data):
        labels = {label for left, right, label in parts if left <= hit.start() < right}
        label = sorted(labels)[0] if len(labels) == 1 else "unmapped_or_ambiguous"
        counts[label] += 1
        footer = hit.group().replace(b"BEGIN", b"END", 1)
        if footer in data[hit.end():min(len(data), hit.end() + 128 * 1024)]:
            counts["paired_header_within_bound"] += 1
        else:
            counts["unpaired_header_within_bound"] += 1
    return counts

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    args = parser.parse_args()
    try:
        if args.binary.stat().st_size > MAX_BINARY:
            raise ValueError("over-size binary")
        counters = classify(args.binary.read_bytes())
    except (OSError, ValueError, struct.error):
        print("ELF marker inspection could not complete; not cleared")
        return 2
    for key in ("readonly_constants", "writable_data", "machine_code",
                "other_or_unknown", "unmapped_or_ambiguous",
                "paired_header_within_bound", "unpaired_header_within_bound"):
        print(f"ELF_MARKER_CLASS {key}={counters.get(key, 0)}")
    print("DIAGNOSTIC ONLY: the strict Docker layer privacy gate remains mandatory")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
