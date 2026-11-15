#!/usr/bin/env python3
"""CI-only real Docker Compose recovery: synthetic SQLite, no network or release.

The adapter changes only artificial digest values into local image tags.
All Docker commands, container replacement and SQLite restore are real.
No production keys, live servers, Docker registry push, or panel logs.
"""
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

BASE = "ghcr.io/smgsp6/3x-ui@sha256:"
OLD = BASE + "a" * 64
BAD = BASE + "b" * 64
OLD_TAG = "vela-ci-recovery-old:local"
BAD_TAG = "vela-ci-recovery-failed:local"
CLI = Path(__file__).resolve().parents[1] / "deploy/vela/vela"

def command(args, env=None, success=True, timeout=240):
    proc = subprocess.run([str(x) for x in args], env=env, text=True,
                          capture_output=True, check=False, timeout=timeout)
    if success and proc.returncode:
        raise AssertionError("Docker recovery check failed (output suppressed)")
    return proc

def check(condition, message):
    if not condition:
        raise AssertionError(message)

def setup(root, docker):
    for name in ("db", "cert", "acme", "secrets", "backups"):
        (root / name).mkdir(mode=0o700)
    token = root / "secrets/vela_bot_token"
    token.write_text("123456:" + secrets.token_urlsafe(35))
    token.chmod(0o600)
    envfile = root / ".env"
    envfile.write_text("XUI_TG_MINIAPP_URL=https://vela.invalid/\n"
                       "XUI_TG_MINIAPP_ADMIN_IDS=1001\nXUI_PORT=2053\n")
    envfile.chmod(0o600)
    (root / "image.ref").write_text(OLD + "\n")
    (root / "release.sequence").write_text("1\n")
    (root / "cert/ci.marker").write_text("cert-before\n")
    (root / "acme/ci.marker").write_text("acme-before\n")
    (root / "compose.yml").write_text("""services:
  vela:
    container_name: vela_panel
    image: ${VELA_IMAGE:?image required}
    network_mode: none
    restart: 'no'
    security_opt: [no-new-privileges:true]
    cap_drop: [ALL]
    environment:
      XUI_IN_DOCKER: 'true'
      XUI_DB_TYPE: sqlite
      XUI_ENABLE_FAIL2BAN: 'false'
      XUI_PORT: '2053'
      XUI_TG_MINIAPP_ENABLED: 'true'
      XUI_TG_MINIAPP_ADMIN_IDS: '1001'
      XUI_TG_MINIAPP_URL: 'https://vela.invalid/'
      XUI_TG_MINIAPP_BOT_TOKEN_FILE: /run/secrets/vela_bot_token
    volumes:
      - ${VELA_HOME:?}/db:/etc/x-ui
      - ${VELA_HOME}/cert:/root/cert
      - ${VELA_HOME}/acme:/root/.acme.sh
      - ${VELA_HOME}/secrets/vela_bot_token:/run/secrets/vela_bot_token:ro
""")
    bridge = root.parent / "bin"
    bridge.mkdir(mode=0o700)
    wrapper = bridge / "docker"
    wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import os,sys\n"
        "args=sys.argv[1:]\n"
        "env=os.environ.copy()\n"
        "if args and args[0]=='compose' and env.get('VELA_IMAGE'):\n"
        f" mapping={{{OLD!r}:{OLD_TAG!r},{BAD!r}:{BAD_TAG!r}}}\n"
        " if env['VELA_IMAGE'] not in mapping: sys.exit(3)\n"
        " env['VELA_IMAGE']=mapping[env['VELA_IMAGE']]\n"
        f"os.execve({docker!r},[{docker!r},*args],env)\n")
    wrapper.chmod(0o700)
    env = os.environ.copy()
    env.update(VELA_HOME=str(root), VELA_HEALTH_ATTEMPTS="20",
               VELA_HEALTH_RETRY_SECS="1", COMPOSE_PROJECT_NAME="vela-recovery-ci",
               PATH=str(bridge) + os.pathsep + os.environ["PATH"])
    return env

def compose(root, env, digest, *args):
    command(["docker", "compose", "--project-directory", root,
             "--env-file", root / ".env", "-f", root / "compose.yml", *args],
            env={**env, "VELA_IMAGE": digest})

def await_ready(root, env):
    for _ in range(45):
        if (root / "db/x-ui.db").is_file():
            result = command(["docker", "exec", "vela_panel", "sh", "-c",
                              "curl -sS --connect-timeout 1 --max-time 2 "
                              "-o /dev/null -w '%{http_code}' "
                              "http://127.0.0.1:2053/tg-miniapp/health"],
                             env=env, success=False, timeout=9)
            if result.returncode == 0 and result.stdout == "204":
                return
        time.sleep(1)
    raise AssertionError("isolated real panel health never reached 204")

def rows(db):
    with sqlite3.connect("file:" + str(db) + "?mode=ro", uri=True) as con:
        check(con.execute("PRAGMA integrity_check").fetchone() == ("ok",),
              "SQLite integrity check failed")
        return con.execute("SELECT id, state FROM vela_ci_recover ORDER BY id").fetchall()

def cli(env, operation, success=True):
    return command(["bash", CLI, operation], env=env, success=success)

def test(root, env):
    print("1/5: Boot real Vela in isolated Docker Compose")
    compose(root, env, OLD, "up", "-d", "--force-recreate")
    await_ready(root, env)
    compose(root, env, OLD, "stop", "-t", "30")
    db = root / "db/x-ui.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE vela_ci_recover (id INTEGER PRIMARY KEY, state TEXT NOT NULL)")
        con.execute("INSERT INTO vela_ci_recover VALUES (1, 'snapshot')")
    check(rows(db) == [(1, "snapshot")], "synthetic baseline invalid")
    compose(root, env, OLD, "start")
    await_ready(root, env)

    print("2/5: CLI creates a real stopped SQLite snapshot")
    cli(env, "backup")
    archives = list((root / "backups").glob("vela-*.tar.gz"))
    check(len(archives) == 1, "CLI backup not unique")
    archive = archives[0]
    check(stat.S_IMODE(archive.stat().st_mode) == 0o600, "backup is not private")
    with tarfile.open(archive, "r:gz") as t:
        members = t.getmembers()
        check(any(m.isfile() and m.name == "db/x-ui.db" for m in members),
              "real SQLite not in backup")
        check(not any(m.name.startswith("secrets/") for m in members),
              "private local token captured in backup")

    print("3/5: Real Docker candidate replaces Vela then fails health")
    compose(root, env, OLD, "stop", "-t", "30")
    compose(root, env, BAD, "up", "-d", "--force-recreate")
    inspect = command(["docker", "inspect", "-f", "{{.Config.Image}}", "vela_panel"],
                      env=env)
    check(inspect.stdout.strip() == BAD_TAG, "candidate image did not replace old")
    with sqlite3.connect(db) as con:
        con.execute("UPDATE vela_ci_recover SET state='candidate-write' WHERE id=1")
    (root / "image.ref").write_text(BAD + "\n")
    (root / "release.sequence").write_text("2\n")
    pending = root / ".pending-update"
    pending.write_text(OLD + "\n" + BAD + "\n" + str(archive) + "\n1\n")
    pending.chmod(0o600)

    print("4/5: Actual vela recover restores Docker image and SQLite snapshot")
    cli(env, "recover")
    check(not pending.exists(), "completed recovery journal retained")
    check((root / "image.ref").read_text().strip() == OLD, "image digest not restored")
    check((root / "release.sequence").read_text().strip() == "1", "sequence not restored")
    check(rows(db) == [(1, "snapshot")], "candidate DB mutation survived rollback")
    failed = list((root / "failed-updates").glob("*/db/x-ui.db"))
    check(len(failed) == 1 and rows(failed[0]) == [(1, "candidate-write")],
          "failed candidate SQLite not quarantined")
    check((root / "cert/ci.marker").read_text() == "cert-before\n",
          "synthetic cert state not restored")
    check((root / "acme/ci.marker").read_text() == "acme-before\n",
          "synthetic ACME state not restored")
    await_ready(root, env)
    result = command(["docker", "inspect", "-f", "{{.Config.Image}}", "vela_panel"],
                     env=env)
    check(result.stdout.strip() == OLD_TAG, "actual Docker image did not roll back")

    print("5/5: Corrupt archive fails closed with existing live data unchanged")
    corrupt = root / "backups/vela-20261115T000000Z-99999.tar.gz"
    corrupt.write_bytes(b"synthetic-invalid-archive")
    corrupt.chmod(0o600)
    pending.write_text(OLD + "\n" + BAD + "\n" + str(corrupt) + "\n1\n")
    pending.chmod(0o600)
    before = db.read_bytes()
    check(cli(env, "recover", success=False).returncode != 0,
          "corrupt recovery unexpectedly succeeded")
    check(db.read_bytes() == before and rows(db) == [(1, "snapshot")],
          "corrupted backup damaged the live SQLite database")
    check(pending.exists() and (root / "image.ref").read_text().strip() == OLD,
          "corrupt restore destroyed recovery evidence")
    print("PASS: real Docker replacement, CLI snapshot recovery and fail-closed backup")

def main():
    check(os.geteuid() == 0 and os.environ.get("GITHUB_ACTIONS") == "true",
          "disposable GitHub CI root execution required")
    docker = shutil.which("docker")
    check(docker and Path(docker).is_absolute(), "real Docker client required")
    with tempfile.TemporaryDirectory(prefix="vela-real-docker-ci-") as temp:
        root = Path(temp) / "vela"
        root.mkdir(mode=0o700)
        env = setup(root, docker)
        try:
            test(root, env)
        finally:
            command([docker, "rm", "-f", "vela_panel"], success=False)
            command([docker, "compose", "--project-directory", root,
                     "--env-file", root / ".env", "-f", root / "compose.yml",
                     "down", "--remove-orphans"],
                    env={**env, "VELA_IMAGE": OLD_TAG}, success=False)

if __name__ == "__main__":
    try:
        main()
    except (AssertionError, OSError, ValueError, sqlite3.Error,
            subprocess.TimeoutExpired):
        print("FAIL: isolated real Docker rollback contract (details suppressed)",
              file=sys.stderr)
        raise SystemExit(1)
