"""Offline verification for Vela PR build order and TLS downgrade guard.

The actual full Go/React/Docker build must still run in GitHub Actions; these
checks catch regressions in the CI source before a reviewer enables it.
"""
from pathlib import Path
import ast
from collections import Counter
import tempfile
import unittest
import test_apply_to_repo as patch_helpers

ROOT = Path(__file__).resolve().parents[1]


class BuildGateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / '.github/workflows/vela-pr-check.yml').read_text()

    def test_privacy_must_finish_before_builds(self):
        w = self.workflow
        self.assertIn('permissions:\n  contents: read', w)
        self.assertIn('persist-credentials: false', w)
        self.assertIn('fetch-depth: 0', w)
        self.assertIn('needs: privacy', w)
        self.assertIn('needs: [privacy, integration, maintenance]', w)
        self.assertIn('python3 vela-development/integration/baseline_privacy_gate.py', w)
        self.assertIn('Strict delta privacy check against immutable upstream baseline', w)
        # Historical upstream fixtures are not an approval for a release.
        self.assertIn('Reject tracked runtime secrets and private files', w)
        self.assertNotIn('docker push', w)
        self.assertNotIn('docker/login-action', w)
        self.assertNotIn('secrets.', w)

    def test_frontend_embed_is_available_before_go_compilation(self):
        w = self.workflow
        positions = [
            w.index('run: npm ci'),
            w.index('run: npm run typecheck'),
            w.index('run: npm test'),
            w.index('run: npm --ignore-scripts run build'),
            w.index('test -s internal/web/dist/index.html'),
            w.index('test -s internal/web/dist/miniapp.html'),
            w.index('run: go test -mod=readonly ./...'),
            w.index('run: go build -mod=readonly -trimpath'),
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('go-version-file: go.mod', w)
        self.assertIn("node-version: '26.13.1'", w)

    def test_each_source_is_modified_once_to_prevent_lost_edits(self):
        tree = ast.parse((ROOT / 'apply_to_repo.py').read_text())
        edited = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'modify':
                if node.args and isinstance(node.args[0], ast.Constant):
                    edited.append(node.args[0].value)
        self.assertGreater(len(edited), 15)
        self.assertFalse({path: count for path, count in Counter(edited).items() if count > 1})

    def test_docker_build_has_no_push_and_runs_after_go(self):
        w = self.workflow
        generated = 'python3 deploy/vela/ci_prepare_dockerfile.py Dockerfile "${RUNNER_TEMP}/VelaCiDockerfile"'
        build = 'docker build --pull --no-cache -f "${RUNNER_TEMP}/VelaCiDockerfile" --tag vela-integration-ci:local .'
        self.assertIn(generated, w)
        self.assertIn(build, w)
        self.assertLess(w.index(generated), w.index(build))
        self.assertNotIn('docker build --pull --no-cache --tag vela-integration-ci:local .', w)
        self.assertIn('docker image inspect vela-integration-ci:local', w)
        self.assertIn('docker image save vela-integration-ci:local | python3 deploy/vela/image_layer_audit.py --stdin', w)
        self.assertIn('name: Clean Docker image build (no push)', w)

    def test_automatic_gate_reuses_one_audited_image_on_development_pushes(self):
        w = self.workflow
        self.assertEqual(w.count("docker build --pull --no-cache -f"), 1)
        self.assertIn("branches: [vela-dev]", w)
        self.assertIn("if: github.event_name != 'pull_request'", w)
        self.assertIn("github.event.repository.private == false", w)
        self.assertIn("npm ci --ignore-scripts", w)
        self.assertNotIn("upload-artifact", w)
        self.assertLess(w.index("Audit every final-image layer"), w.index("Verify genuine HTTPS"))
        self.assertLess(w.index("Audit every final-image layer"), w.index("Run actual Vela recover"))

    def test_applied_patch_refuses_tls_http_downgrade_only_in_vela_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = patch_helpers.PatchTests()
            repo = h.make_repo(Path(tmp))
            h.execute(repo)
            web = (repo / 'internal/web/web.go').read_text()
            self.assertIn('if tgminiapp.Enabled() {\n                    _ = listener.Close()', web)
            self.assertIn('refusing silent HTTP downgrade', web)
            self.assertIn('logger.Info("Web server running HTTP on", listener.Addr())', web)
            self.assertIn('c.GetCertificate = reloader.GetCertificate', web)


if __name__ == '__main__':
    unittest.main()
