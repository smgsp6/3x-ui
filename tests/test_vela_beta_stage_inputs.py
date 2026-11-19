"""Check hosted beta preflight without downloads or workflow dispatch."""
import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy/vela"))
stage = importlib.import_module("beta-stage-inputs")


class StageInputsTests(unittest.TestCase):
    def test_missing_input_lock_entries_fail_before_network(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(stage, "download") as download:
            with self.assertRaisesRegex(ValueError, "three base digests"):
                stage.stage({"bases": {}, "files": {}, "trivy": {}, "db": {}}, Path(directory))
            download.assert_not_called()

    def test_registry_redirect_strips_bearer_auth(self):
        handler = stage.AllowedRedirect({"ghcr.io", "pkg-containers.githubusercontent.com"})
        request = Request("https://ghcr.io/registry", headers={"Authorization": "fixture"})
        redirected = handler.redirect_request(request, None, 307, "", {},
                                              "https://pkg-containers.githubusercontent.com/blob")
        self.assertIsNone(redirected.get_header("Authorization"))
        with self.assertRaisesRegex(ValueError, "unexpected redirect"):
            handler.redirect_request(request, None, 307, "", {}, "http://127.0.0.1/internal")
