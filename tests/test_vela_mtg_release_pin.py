"""CI-only release pin guard tests, never include or execute private keys."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "DockerInit.sh"
PIN = ROOT / "deploy/vela/ci_pin_mtg_dockerinit.sh"
VERIFY = ROOT / "deploy/vela/ci_verify_mtg_archive.sh"

class MTGReleasePinTests(unittest.TestCase):
    def test_patches_temporary_copy_not_upstream_source(self):
        original = SOURCE.read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            scratch = Path(temp) / "DockerInit.sh"
            scratch.write_bytes(original)
            result = subprocess.run(["sh", str(PIN), str(scratch)], capture_output=True)
            self.assertEqual(result.returncode, 0, "exact upstream source should pass")
            revised = scratch.read_text()
            self.assertIn("MTG_MULTI_VER=v1.16.1\n", revised)
            verifier = 'sh /app/deploy/vela/ci_verify_mtg_archive.sh "$PLATFORM" "${MTG_PKG}.tar.gz"'
            self.assertIn(verifier, revised)
            self.assertLess(revised.index(verifier), revised.index('tar -xzf "${MTG_PKG}.tar.gz"'))
        self.assertEqual(SOURCE.read_bytes(), original)

    def test_unknown_upstream_is_rejected_without_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            scratch = Path(temp) / "DockerInit.sh"
            altered = SOURCE.read_text().replace(
                "https://api.github.com/repos/mhsanaei/mtg-multi/releases/latest",
                "https://unreviewed.invalid/releases/latest")
            scratch.write_text(altered)
            check = subprocess.run(["sh", str(PIN), str(scratch)], capture_output=True)
            self.assertNotEqual(check.returncode, 0)
            self.assertEqual(scratch.read_text(), altered)

    def test_modified_archive_rejected_for_all_arches(self):
        for arch in ("amd64", "arm64", "armv6", "armv7", "386"):
            with self.subTest(arch=arch), tempfile.TemporaryDirectory() as temp:
                filename = f"mtg-multi-1.16.1-linux-{arch}.tar.gz"
                (Path(temp) / filename).write_bytes(b"synthetic-not-real-mtg-release")
                check = subprocess.run(["sh", str(VERIFY), arch, filename],
                                       cwd=temp, capture_output=True)
                self.assertNotEqual(check.returncode, 0)
        check = subprocess.run(["sh", str(VERIFY), "mips", "unlisted.tar.gz"],capture_output=True)
        self.assertNotEqual(check.returncode, 0)

if __name__ == "__main__":
    unittest.main()
