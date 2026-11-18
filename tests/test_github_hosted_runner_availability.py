"""CI-only check that Vela's tests really execute on GitHub-hosted Linux.

This has no network, production, VPS, credential, or deployment operations.
Local unit test discovery skips the check outside GitHub Actions.
"""
import os
import unittest


class GitHubHostedRunnerAvailabilityTest(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("GITHUB_ACTIONS") == "true",
        "GitHub-hosted CI environment check only",
    )
    def test_standard_github_hosted_linux_runner(self):
        self.assertEqual(os.environ.get("GITHUB_REPOSITORY"), "smgsp6/3x-ui")
        self.assertEqual(os.environ.get("RUNNER_ENVIRONMENT"), "github-hosted")
        self.assertEqual(os.environ.get("RUNNER_OS"), "Linux")


if __name__ == "__main__":
    unittest.main()
