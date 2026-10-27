import sys
import unittest
from pathlib import Path

from fastmcp.server.auth import AccessToken

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from oauth import github_login_is_allowed  # noqa: E402


class GitHubAllowlistTests(unittest.TestCase):
    def test_accepts_allowlisted_login_case_insensitively(self):
        token = AccessToken(
            token="secret",
            client_id="1",
            scopes=["read:user"],
            claims={"upstream_claims": {"login": "MarkRz-0"}},
        )

        self.assertTrue(github_login_is_allowed(token, {"markrz-0"}))

    def test_rejects_other_or_missing_identity(self):
        other = AccessToken(
            token="secret",
            client_id="2",
            scopes=["read:user"],
            claims={"upstream_claims": {"login": "someone-else"}},
        )
        missing = AccessToken(
            token="secret", client_id="3", scopes=["read:user"], claims={}
        )

        self.assertFalse(github_login_is_allowed(other, {"markrz-0"}))
        self.assertFalse(github_login_is_allowed(missing, {"markrz-0"}))
        self.assertFalse(github_login_is_allowed(None, {"markrz-0"}))


if __name__ == "__main__":
    unittest.main()
