import sqlite3
import os
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastmcp.server.auth import AccessToken

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("MOODLE_USERNAME", "local-test@example.edu")
os.environ.setdefault("MOODLE_PASSWORD", "local-test-password")

from accounts import (  # noqa: E402
    AccountStore,
    CredentialsNotConfigured,
    InvalidSetupToken,
)
from identity import github_identity_from_token  # noqa: E402


class AccountStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "accounts.db"
        self.store = AccountStore(str(self.database_path), "k" * 64)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_invite_and_credentials_are_encrypted_at_rest(self):
        account = self.store.invite("12345", "friend")
        with self.assertRaises(CredentialsNotConfigured):
            self.store.get_credentials(account.id)

        self.store.set_credentials(account.id, "student@example.edu", "secret-pass")
        self.assertEqual(
            self.store.get_credentials(account.id),
            ("student@example.edu", "secret-pass"),
        )
        database_bytes = self.database_path.read_bytes()
        self.assertNotIn(b"student@example.edu", database_bytes)
        self.assertNotIn(b"secret-pass", database_bytes)

    def test_setup_token_is_single_use(self):
        account = self.store.invite("12345", "friend")
        token = self.store.create_setup_token(account.id, 600)
        self.assertEqual(
            self.store.account_for_setup_token(token).github_login, "friend"
        )
        self.store.set_credentials_with_setup_token(token, "student@example.edu", "pw")
        self.assertIsNone(self.store.account_for_setup_token(token))
        with self.assertRaises(InvalidSetupToken):
            self.store.set_credentials_with_setup_token(token, "other@example.edu", "pw2")

    def test_expired_setup_token_is_rejected(self):
        account = self.store.invite("12345", "friend")
        token = self.store.create_setup_token(account.id, 600)
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute("UPDATE setup_tokens SET expires_at = 0")
            connection.commit()
        self.assertIsNone(self.store.account_for_setup_token(token))

    def test_bootstrap_is_one_time_and_disabled_account_stays_disabled(self):
        allowed = {"owner"}
        self.assertTrue(
            self.store.authorize_identity(
                "777", "Owner", allowed, ("owner@example.edu", "pw")
            )
        )
        account = self.store.get_by_github_id("777")
        self.assertEqual(self.store.get_credentials(account.id), ("owner@example.edu", "pw"))
        self.assertTrue(self.store.set_enabled("777", False))
        self.assertFalse(self.store.authorize_identity("777", "RenamedOwner", allowed))
        self.assertFalse(self.store.get_by_github_id("777").enabled)


class IdentityTests(unittest.TestCase):
    def test_extracts_immutable_github_identity(self):
        token = AccessToken(
            token="secret",
            client_id="client",
            scopes=["read:user"],
            claims={"upstream_claims": {"sub": "12345", "login": "Friend"}},
        )
        self.assertEqual(github_identity_from_token(token), ("12345", "Friend"))

    def test_rejects_missing_identity(self):
        self.assertIsNone(github_identity_from_token(None))


if __name__ == "__main__":
    unittest.main()
