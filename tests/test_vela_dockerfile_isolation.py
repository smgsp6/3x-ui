"""No upstream modification and deletion must stay in apk-install layer."""
import importlib.util
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("generator", ROOT / "deploy/vela/ci_prepare_dockerfile.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class DockerfileIsolationTests(unittest.TestCase):
    def test_actual_upstream_dockerfile_preserved(self):
        before = (ROOT / "Dockerfile").read_text()
        result = mod.render(before)
        self.assertEqual((ROOT / "Dockerfile").read_text(), before)
        self.assertEqual(result.count("fail2ban/tests/*"), 1)
        self.assertIn("openssl \\\n  && find ", result)
        self.assertLess(result.index("fail2ban/tests/*"), result.index("COPY --from=builder /app/build"))
        self.assertIn("&& fail2ban-client --version", result)
        self.assertNotIn("fail2ban/tests/*", before)

    def test_unknown_upstream_fails_closed(self):
        with self.assertRaises(ValueError):
            mod.render("FROM alpine\nRUN apk add fail2ban\n")

    def test_cannot_overwrite_original(self):
        # Entrypoint can write to a fresh scratch location only.
        with TemporaryDirectory() as temp:
            dest = Path(temp) / "Dockerfile.test"
            dest.write_text(mod.render((ROOT / "Dockerfile").read_text()))
            self.assertIn("fail2ban/tests/*", dest.read_text())

if __name__ == "__main__":
    unittest.main()
