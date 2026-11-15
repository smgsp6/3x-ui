#!/usr/bin/env python3
"""Read-only Vela personal-beta filesystem readiness gate.

Run on a dedicated test host, never on an unapproved production server.
No Docker commands, network calls, secret logging, or file modifications.
A pass is NOT authorization to install or update Vela.
"""
import argparse
import ipaddress
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

IMAGE_PATTERN = re.compile(r"ghcr\.io/smgsp6/3x-ui@sha256:[a-f0-9]{64}\Z", re.ASCII)
ID_PATTERN = re.compile(r"[1-9][0-9]*\Z", re.ASCII)
ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z", re.ASCII)
SEQUENCE_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,15})\Z", re.ASCII)


class PreflightFailure(Exception):
    """An untrusted local file violates the installation layout contract."""


def verify_path(path: Path, kind: str, private: bool = False) -> None:
    try:
        meta = path.lstat()
    except OSError:
        raise PreflightFailure(f"missing {kind}") from None
    if kind in {"home", "db", "cert", "acme", "secrets"}:
        if not stat.S_ISDIR(meta.st_mode):
            raise PreflightFailure(f"invalid {kind} directory or symlink")
        if meta.st_mode & 0o022:
            raise PreflightFailure(f"writable {kind} directory")
        if private and meta.st_mode & 0o077:
            raise PreflightFailure(f"overly accessible {kind} directory")
    else:
        if not stat.S_ISREG(meta.st_mode):
            raise PreflightFailure(f"invalid {kind} file or symlink")
        if meta.st_mode & (0o077 if private else 0o022):
            raise PreflightFailure(f"unsafe {kind} file permissions")


def read_private_text(path: Path, label: str, maximum: int = 16384) -> str:
    verify_path(path, label, private=True)
    if path.stat().st_size > maximum or path.stat().st_size == 0:
        raise PreflightFailure(f"invalid {label} size")
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeError, OSError):
        raise PreflightFailure(f"invalid {label} encoding") from None


def parse_env(path: Path) -> dict[str, str]:
    raw = read_private_text(path, "env")
    if "\x00" in raw or "\r" in raw or raw.startswith("\ufeff"):
        raise PreflightFailure("invalid env format")
    parsed: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            raise PreflightFailure("invalid env assignment")
        key, value = line.split("=", 1)
        if not ENV_KEY.fullmatch(key) or key in parsed:
            raise PreflightFailure("invalid or duplicate env key")
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise PreflightFailure("control-character env value")
        # The runtime uses Docker Compose .env parsing, not shell sourcing.
        # Reject ambiguous quoting, comments, substitution and whitespace on
        # security-critical values rather than attempt to interpret them.
        parsed[key] = value
    return parsed


def reject_unsafe_env_variables(env: dict[str, str]) -> None:
    # Compose reads .env as input, but credentials must reside only in local
    # Docker Secret files, never in env, process arguments or public CI logs.
    # Also refuse Docker/Compose environment directives that could redirect
    # an operator's deployment to a different daemon or configuration.
    # These checks are intentionally independent of whether the reviewed
    # Compose file currently interpolates a given variable.
    sensitive_markers = ("TOKEN", "PASSWORD", "PASSWD", "SECRET", "PRIVATE_KEY", "API_KEY")
    for name in env:
        normalized = name.upper()
        if (normalized.startswith(("DOCKER_", "COMPOSE_")) or
                any(marker in normalized for marker in sensitive_markers)):
            # Never print names or values: a malicious env key itself could
            # contain an identifier or credential.
            raise PreflightFailure("unsafe credential or Docker/Compose variable in env")


def validate_url(value: str) -> None:
    if any(c.isspace() for c in value) or any(c in value for c in '$\\"\''):
        raise PreflightFailure("invalid Telegram HTTPS URL")
    try:
        u = urlsplit(value)
        host = u.hostname
        port = u.port
    except ValueError:
        raise PreflightFailure("invalid Telegram HTTPS URL") from None
    if u.scheme != "https" or not host or u.username or u.password or u.query or u.fragment:
        raise PreflightFailure("invalid Telegram HTTPS URL")
    if port is not None and not (1 <= port <= 65535):
        raise PreflightFailure("invalid Telegram HTTPS port")
    if not re.fullmatch(r"[a-z0-9.-]+", host, re.IGNORECASE | re.ASCII):
        raise PreflightFailure("invalid Telegram HTTPS hostname")
    if "." not in host or host.startswith(".") or host.endswith(".") or ".." in host:
        raise PreflightFailure("invalid public Telegram hostname")
    # All example.com/net/org subdomains are documentation placeholders too.
    # The published runtime.env.example uses vela.example.com; accepting that
    # value would incorrectly approve an unreachable Mini App for personal beta.
    reserved_domains = ("example.com", "example.net", "example.org")
    if (host == "localhost" or
            host.endswith((".localhost", ".local", ".test", ".invalid", ".example")) or
            any(host == domain or host.endswith("." + domain) for domain in reserved_domains)):
        raise PreflightFailure("placeholder or local Telegram hostname")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise PreflightFailure("Telegram hostname must be a DNS name")
    if u.path and not u.path.startswith("/"):
        raise PreflightFailure("invalid Telegram HTTPS path")


def validate(home: Path, template: Path | None = None) -> None:
    if not home.is_absolute():
        raise PreflightFailure("VELA_HOME must be absolute")
    # Checking only home.lstat() is insufficient: /safe/link/vela may be a
    # real directory accessed through a symlinked parent. The CLI resolves
    # VELA_HOME before operating; never let this preflight approve a
    # different path or parent traversal spelling.
    if ".." in home.parts:
        raise PreflightFailure("VELA_HOME parent traversal is forbidden")
    for ancestor in (home, *home.parents):
        try:
            mode = ancestor.lstat().st_mode
        except OSError:
            raise PreflightFailure("VELA_HOME path component is unavailable") from None
        if stat.S_ISLNK(mode):
            raise PreflightFailure("VELA_HOME contains a symlinked path component")
    verify_path(home, "home", private=True)
    env = parse_env(home / ".env")
    reject_unsafe_env_variables(env)
    # The maintenance CLI passes VELA_HOME as a process environment variable.
    # The shipped runtime.env.example intentionally omits it. The inspected
    # absolute path is authoritative; still refuse any conflicting .env value.
    if "VELA_HOME" in env and env["VELA_HOME"] != str(home):
        raise PreflightFailure("VELA_HOME differs from inspected directory")
    if env.get("XUI_TG_MINIAPP_ENABLED", "true") != "true":
        raise PreflightFailure("Telegram Mini App must be enabled")
    if env.get("XUI_DB_TYPE", "sqlite") != "sqlite":
        raise PreflightFailure("personal beta requires SQLite")
    ids = env.get("XUI_TG_MINIAPP_ADMIN_IDS", "").split(",")
    if len(ids) == 0 or len(ids) > 32 or any(not ID_PATTERN.fullmatch(s) or int(s) > 2**63 - 1 for s in ids) or len(set(ids)) != len(ids):
        raise PreflightFailure("invalid Telegram administrator allowlist")
    validate_url(env.get("XUI_TG_MINIAPP_URL", ""))
    port = env.get("XUI_PORT", "2053")
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise PreflightFailure("invalid management port")
    for folder in ("db", "cert", "acme", "secrets"):
        verify_path(home / folder, folder, private=True)
    token = read_private_text(home / "secrets" / "vela_bot_token", "bot secret", maximum=512)
    token = token.removesuffix("\n")
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token, re.ASCII):
        raise PreflightFailure("invalid bot secret format")
    # Do not print, log or return the secret or Telegram IDs.
    verify_path(home / "compose.yml", "compose")
    if template is not None:
        verify_path(template, "reviewed compose template")
        if (home / "compose.yml").read_bytes() != template.read_bytes():
            raise PreflightFailure("compose does not match reviewed Vela template")
    image = read_private_text(home / "image.ref", "image reference", maximum=256).strip()
    if not IMAGE_PATTERN.fullmatch(image):
        raise PreflightFailure("image must be the reviewed GHCR SHA256 digest")
    if "VELA_IMAGE" in env and env["VELA_IMAGE"] != image:
        raise PreflightFailure("image reference mismatch")
    seq = read_private_text(home / "release.sequence", "release sequence", maximum=32).strip()
    if not SEQUENCE_PATTERN.fullmatch(seq) or int(seq) > 9007199254740991:
        raise PreflightFailure("invalid release anti-rollback sequence")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("home", type=Path, help="Existing isolated test-host VELA_HOME")
    args = parser.parse_args()
    try:
        validate(args.home, Path(__file__).with_name("compose.host.yml"))
    except PreflightFailure as exc:
        print(f"VELA BETA PRECHECK FAIL: {exc}")
        return 1
    print("VELA BETA PRECHECK PASS: local layout, secrets permissions, allowlist and pinned image metadata")
    print("NOT APPROVED FOR INSTALL: still requires real Telegram WebView, proxy TLS, Xray network and recovery verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
