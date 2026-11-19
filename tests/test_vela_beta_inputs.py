"""Exercise lock validation with fixed source and synthetic files, without Docker."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("beta_inputs", ROOT / "deploy/vela/beta-inputs.py")
inputs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inputs)


class BetaInputsTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.context = self.directory / "context"
        self.context.mkdir()
        self.staged = self.directory / "downloads"
        self.digest = hashlib.sha256(b"fixture").hexdigest()
        self.lock = {
            "bases": {stage: f"{repo}@sha256:{'1' * 64}" for stage, repo in inputs.BASES.items()},
            "files": {},
        }
        for name, prefix in inputs.ASSETS.items():
            url = prefix + ("" if prefix.endswith(("v26.11.9/", "v1.16.1/")) else "v-fixture/") + name
            self.stage(name, url)
        for stage in ("builder", "runtime"):
            self.stage(f"{stage}/fixture.apk",
                       "https://dl-cdn.alpinelinux.org/alpine/v3.22/main/x86_64/fixture.apk")
        for file in ("Dockerfile", "DockerInit.sh"):
            fixed = subprocess.check_output(["git", "show", f"9ef190a5:{file}"], cwd=ROOT)
            (self.context / file).write_bytes(fixed)
        subprocess.run(["python3", str(ROOT / "deploy/vela/ci_prepare_dockerfile.py"),
                        str(self.context / "Dockerfile"), str(self.context / "VelaCandidateDockerfile")],
                       check=True, capture_output=True)

    def stage(self, name, url):
        self.lock["files"][name] = {"url": url, "sha256": self.digest}
        file = self.staged / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"fixture")

    def prepare(self, digest=None):
        data = json.dumps(self.lock).encode()
        path = self.directory / "lock.json"
        path.write_bytes(data)
        return inputs.prepare(path, digest or hashlib.sha256(data).hexdigest(),
                              self.staged, self.context)

    def test_pins_fixed_recipe_and_disables_asset_downloads(self):
        self.assertEqual(self.prepare(), self.lock["bases"]["runtime"])
        recipe = (self.context / "VelaCandidateDockerfile").read_text()
        self.assertEqual(recipe.count("apk add --no-network"), 2)
        self.assertIn("GOTOOLCHAIN=local go build -mod=readonly", recipe)
        self.assertIn("RUN --network=none", recipe)
        init = self.context / "DockerInit.sh"
        self.assertIn("ci_verify_mtg_archive.sh", init.read_text())
        self.assertNotIn("curl ", init.read_text())
        subprocess.run(["sh", "-n", str(init)], check=True)

    def test_rejects_mutable_base(self):
        self.lock["bases"]["runtime"] = "docker.io/library/alpine:latest"
        with self.assertRaisesRegex(ValueError, "official repository and digest"):
            self.prepare()

    def test_rejects_unapproved_lock(self):
        with self.assertRaisesRegex(ValueError, "lock digest mismatch"):
            self.prepare("f" * 64)

    def test_rejects_altered_download(self):
        (self.staged / "Xray-linux-64.zip").write_bytes(b"wrong bytes")
        with self.assertRaisesRegex(ValueError, "input digest mismatch"):
            self.prepare()
