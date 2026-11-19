"""Offline checks for the fixed-source private image delivery guard."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/vela/beta-image.sh"


class BetaDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        gh = root / "gh"
        gh.write_text("""#!/bin/sh
case "$*" in
    *jobs*) printf '{"total_count":4,"jobs":[{"conclusion":"success"},{"conclusion":"success"},{"conclusion":"success"},{"conclusion":"success"}]}';;
    *actions/runs*) printf '{"head_sha":"9ef190a504221c95925b5224005355bd1313c147","head_branch":"vela-dev","path":".github/workflows/vela-pr-check.yml","conclusion":"success"}';;
    "api -i user") printf 'X-OAuth-Scopes: read:packages\n';;
    "api user --jq .login"|"user --jq .login") printf 'fixture-reader\n';;
    *versions*) printf '%s\n' "$FAKE_TAG";;
    *packages/container*) printf '%s\n' "$FAKE_VISIBILITY";;
    *) exit 1;;
esac
""")
        gh.chmod(0o700)
        self.env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}",
                        FAKE_VISIBILITY="private", FAKE_TAG="")

    def command(self, *args, **overrides):
        return subprocess.run(["bash", str(SCRIPT), *args],
                              env=dict(self.env, **overrides), capture_output=True, text=True)

    def test_private_package_and_unused_tag_pass(self):
        self.assertEqual(self.command("precheck").returncode, 0)

    def test_public_package_and_existing_tag_are_rejected(self):
        public = self.command("precheck", FAKE_VISIBILITY="public")
        existing = self.command("precheck", FAKE_TAG="vela-beta-9ef190a504221c95925b5224005355bd1313c147")
        self.assertIn("Existing private GHCR package required", public.stderr)
        self.assertIn("Do not overwrite", existing.stderr)
        self.assertNotEqual(public.returncode, 0)
        self.assertNotEqual(existing.returncode, 0)

    def test_publish_and_verify_require_explicit_inputs(self):
        self.assertIn("acknowledgment required", self.command("publish").stderr)
        self.assertIn("config ID is required", self.command("verify", EXPECTED_CONFIG_ID="").stderr)

    def test_verify_refuses_changed_remote_manifest_before_pull(self):
        root = Path(self.temp.name)
        (root / "git").write_text("""#!/bin/sh
case "$*" in
    *--show-toplevel) pwd;;
    *"rev-parse HEAD") printf '%s\n' "$APPROVED_DELIVERY_SHA";;
    *status*) exit 0;;
    *) exit 1;;
esac
""")
        (root / "docker").write_text("""#!/bin/sh
case "$*" in
    "context show") echo default;;
    "context inspect "*) echo unix:///var/run/docker.sock;;
    "info "*) echo verifier-daemon;;
    "login "*) cat >/dev/null;;
    "buildx imagetools inspect "*) printf '{"digest":"%s"}' "$FAKE_REMOTE_DIGEST";;
    "pull "*) touch "$XDG_RUNTIME_DIR/pull-called"; exit 1;;
    *) exit 1;;
esac
""")
        for name in ("git", "docker"):
            (root / name).chmod(0o700)
        result = self.command(
            "verify", GH_TOKEN="synthetic", APPROVED_DELIVERY_SHA="1" * 40,
            VELA_EXCLUSIVE_DOCKER="YES", XDG_RUNTIME_DIR=str(root), PUBLISH_DOCKER_ID="publisher",
            EXPECTED_CONFIG_ID="sha256:" + "a" * 64, EXPECTED_PUSH_DIGEST="sha256:" + "b" * 64,
            FAKE_REMOTE_DIGEST="sha256:" + "c" * 64,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Remote manifest differs", result.stderr)
        self.assertFalse((root / "pull-called").exists())
        self.assertNotIn("Verified pull reference", result.stdout)
