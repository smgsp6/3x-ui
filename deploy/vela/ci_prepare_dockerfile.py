#!/usr/bin/env python3
"""Generate a Vela-only experimental Dockerfile while leaving upstream untouched.

Remove Fail2ban test .pyc files within the SAME RUN that installs fail2ban:
a later Docker layer deletion would retain private-key fixtures in history.
Fail closed if the upstream build recipe no longer matches exactly.
"""
import argparse
from pathlib import Path

ORIGINAL = "  bash \\\n  curl \\\n  openssl\n\nCOPY --from=builder"
REPLACEMENT = (
    "  bash \\\n  curl \\\n  openssl \\\n"
    "  && find /usr/lib -type f -name '*.pyc' -path '*/fail2ban/tests/*' -delete \\\n"
    "  && fail2ban-client --version >/dev/null\n\nCOPY --from=builder"
)

def render(text: str) -> str:
    if text.count(ORIGINAL) != 1:
        raise ValueError("upstream Dockerfile layout changed: manual review required")
    if text.count("FROM alpine\n") != 1:
        raise ValueError("upstream runtime base stage changed")
    if not text.count("  fail2ban \\\n") == 1:
        raise ValueError("upstream Fail2ban installation changed")
    pin_anchor = 'RUN ./DockerInit.sh "$TARGETARCH" "$TARGETVARIANT"'
    if text.count(pin_anchor) != 1:
        raise ValueError("upstream DockerInit invocation changed; manual review required")
    updated = text.replace(ORIGINAL, REPLACEMENT)
    updated = updated.replace(
        pin_anchor,
        "RUN sh deploy/vela/ci_pin_mtg_dockerinit.sh DockerInit.sh\n" + pin_anchor)
    if updated == text or updated.count("fail2ban/tests/*") != 1:
        raise ValueError("could not generate audited Fail2ban test cleanup")
    return updated

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.destination.resolve():
        parser.error("original Dockerfile must not be modified")
    result = render(args.source.read_text(encoding="utf-8"))
    args.destination.write_text(result, encoding="utf-8")
    print("Vela experimental Dockerfile generated; original untouched")

if __name__ == "__main__":
    main()
