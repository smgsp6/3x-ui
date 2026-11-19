"""Real Docker Compose V2 expansion of Vela's reviewed host-network template.

Uses only temporary synthetic files; does not start containers or contact the
Docker daemon. No real image, Telegram bot or production server is involved.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "vela"
TEMPLATE = DEPLOY / "compose.host.yml"
spec = importlib.util.spec_from_file_location("beta_preflight", DEPLOY / "beta_preflight.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ComposeContractTests(unittest.TestCase):
    def test_reviewed_compose_matches_preflight_and_runtime_expansion(self):
        with tempfile.TemporaryDirectory(prefix="vela-compose-synthetic-") as scratch:
            home = Path(scratch) / "vela"
            home.mkdir(mode=0o700)
            for name in ("db", "cert", "acme", "secrets"):
                (home / name).mkdir(mode=0o700)
            (home / "compose.yml").write_bytes(TEMPLATE.read_bytes())
            (home / "compose.yml").chmod(0o644)
            (home / ".env").write_text(
                "XUI_TG_MINIAPP_ADMIN_IDS=1001\n"
                "XUI_TG_MINIAPP_URL=https://panel.vela-local-ci.org/app/\n"
                "XUI_PORT=2053\n"
                "TZ=Asia/Tokyo\n",
                encoding="utf-8",
            )
            (home / ".env").chmod(0o600)
            token = home / "secrets" / "vela_bot_token"
            token.write_text("12345:synthetic_only_fixture", encoding="ascii")
            token.chmod(0o600)
            image = "ghcr.io/smgsp6/3x-ui@sha256:" + "a" * 64
            image_ref = home / "image.ref"
            image_ref.write_text(image + "\n", encoding="ascii")
            image_ref.chmod(0o600)
            release_floor = home / "release.sequence"
            release_floor.write_text("0\n", encoding="ascii")
            release_floor.chmod(0o600)

            # Never relax the real preflight's sensitive-file permissions to
            # satisfy synthetic CI fixtures; create reviewed test files with
            # the same owner-only permissions expected on a private host.
            self.assertEqual(image_ref.stat().st_mode & 0o777, 0o600)
            self.assertEqual(release_floor.stat().st_mode & 0o777, 0o600)
            # Preflight and Compose must agree on the very same candidate.
            gate.validate(home, TEMPLATE)
            env = os.environ.copy()
            env["VELA_HOME"] = str(home)
            env["VELA_IMAGE"] = image
            p = subprocess.run(
                ["docker", "compose", "--project-directory", str(home),
                 "--env-file", str(home / ".env"), "-f", str(home / "compose.yml"),
                 "config", "--format", "json"],
                env=env, capture_output=True, text=True, timeout=30, check=False,
            )
            self.assertEqual(p.returncode, 0, "synthetic Compose expansion failed")
            config = json.loads(p.stdout)
            services = config.get("services", {})
            self.assertEqual(set(services), {"vela"})
            vela = services["vela"]
            self.assertEqual(vela["image"], image)
            self.assertEqual(vela["network_mode"], "host")
            self.assertFalse(vela.get("privileged", False))
            self.assertFalse(vela.get("ports"))
            self.assertFalse(vela.get("devices"))
            self.assertIn("no-new-privileges:true", vela.get("security_opt", []))
            self.assertFalse(vela.get("cap_add"))
            self.assertEqual(set(vela.get("cap_drop", [])), {"NET_ADMIN", "NET_RAW"})
            variables = vela["environment"]
            self.assertEqual(variables["XUI_ENABLE_FAIL2BAN"], "false")
            self.assertEqual(variables["XUI_TG_MINIAPP_ENABLED"], "true")
            self.assertEqual(variables["XUI_TG_MINIAPP_ADMIN_IDS"], "1001")
            self.assertEqual(variables["XUI_TG_MINIAPP_BOT_TOKEN_FILE"],
                             "/run/secrets/vela_bot_token")
            self.assertNotIn("XUI_TG_MINIAPP_BOT_TOKEN", variables)
            self.assertNotIn("synthetic_only_fixture", p.stdout)
            secrets = vela.get("secrets", [])
            self.assertEqual(len(secrets), 1)
            self.assertEqual(secrets[0]["source"], "vela_bot_token")
            self.assertEqual(secrets[0]["target"], "/run/secrets/vela_bot_token")
            self.assertEqual(config["secrets"]["vela_bot_token"]["file"],
                             str(token))
            mounts = {item["target"]: item for item in vela.get("volumes", [])}
            self.assertEqual(set(mounts), {"/etc/x-ui", "/root/cert", "/root/.acme.sh"})
            for target, folder in (("/etc/x-ui", "db"), ("/root/cert", "cert"),
                                   ("/root/.acme.sh", "acme")):
                self.assertEqual(mounts[target]["type"], "bind")
                self.assertEqual(mounts[target]["source"], str(home / folder))
            self.assertNotIn("/var/run/docker.sock", p.stdout)


if __name__ == "__main__":
    unittest.main()
