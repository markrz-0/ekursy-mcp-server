from __future__ import annotations

import base64
import hashlib
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class AccountError(RuntimeError):
    pass


class AccountNotFound(AccountError):
    pass


class CredentialsNotConfigured(AccountError):
    pass


class InvalidSetupToken(AccountError):
    pass


class CredentialDecryptionError(AccountError):
    pass


@dataclass(frozen=True)
class Account:
    id: str
    github_user_id: str
    github_login: str
    enabled: bool
    has_credentials: bool


class CredentialCipher:
    """Authenticated encryption derived from a high-entropy server secret."""

    def __init__(self, secret: str) -> None:
        if len(secret) < 32:
            raise ValueError("CREDENTIAL_ENCRYPTION_KEY must be at least 32 characters")
        derived_key = hashlib.sha256(secret.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(derived_key))

    def encrypt(self, value: str) -> bytes:
        return self._fernet.encrypt(value.encode("utf-8"))

    def decrypt(self, value: bytes) -> str:
        try:
            return self._fernet.decrypt(value).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise CredentialDecryptionError(
                "Stored credentials cannot be decrypted with the configured key"
            ) from exc


class AccountStore:
    def __init__(self, database_path: str, encryption_key: str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._cipher = CredentialCipher(encryption_key)
        self._lock = threading.RLock()
        self.initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    github_user_id TEXT UNIQUE NOT NULL,
                    github_login TEXT NOT NULL,
                    moodle_username_encrypted BLOB,
                    moodle_password_encrypted BLOB,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS setup_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS setup_tokens_user_id_idx
                    ON setup_tokens(user_id);
                """
            )

    @staticmethod
    def _row_to_account(row: sqlite3.Row) -> Account:
        return Account(
            id=row["id"],
            github_user_id=row["github_user_id"],
            github_login=row["github_login"],
            enabled=bool(row["enabled"]),
            has_credentials=(
                row["moodle_username_encrypted"] is not None
                and row["moodle_password_encrypted"] is not None
            ),
        )

    def get_by_github_id(self, github_user_id: str) -> Account | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE github_user_id = ?",
                (github_user_id,),
            ).fetchone()
        return self._row_to_account(row) if row else None

    def get_by_local_id(self, user_id: str) -> Account | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return self._row_to_account(row) if row else None

    def list_accounts(self) -> list[Account]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM users ORDER BY github_login COLLATE NOCASE"
            ).fetchall()
        return [self._row_to_account(row) for row in rows]

    def invite(self, github_user_id: str, github_login: str) -> Account:
        github_user_id = github_user_id.strip()
        github_login = github_login.strip()
        if not github_user_id or not github_login:
            raise ValueError("GitHub user ID and login are required")

        now = int(time.time())
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    id, github_user_id, github_login, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(github_user_id) DO UPDATE SET
                    github_login = excluded.github_login,
                    enabled = 1,
                    updated_at = excluded.updated_at
                """,
                (str(uuid.uuid4()), github_user_id, github_login, now, now),
            )
        account = self.get_by_github_id(github_user_id)
        if account is None:
            raise AccountError("Failed to create account")
        return account

    def authorize_identity(
        self,
        github_user_id: str,
        github_login: str,
        bootstrap_logins: set[str],
        bootstrap_credentials: tuple[str, str] | None = None,
    ) -> bool:
        account = self.get_by_github_id(github_user_id)
        if account is not None:
            if account.github_login != github_login:
                with self._lock, self._connect() as connection:
                    connection.execute(
                        "UPDATE users SET github_login = ?, updated_at = ? "
                        "WHERE github_user_id = ?",
                        (github_login, int(time.time()), github_user_id),
                    )
            return bool(account and account.enabled)

        if github_login.lower() not in bootstrap_logins:
            return False

        account = self.invite(github_user_id, github_login)
        if bootstrap_credentials and not account.has_credentials:
            self.set_credentials(
                account.id, bootstrap_credentials[0], bootstrap_credentials[1]
            )
        return True

    def set_enabled(self, github_user_id: str, enabled: bool) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET enabled = ?, updated_at = ? WHERE github_user_id = ?",
                (int(enabled), int(time.time()), github_user_id),
            )
        return cursor.rowcount == 1

    def set_credentials(self, user_id: str, username: str, password: str) -> None:
        if not username or not password:
            raise ValueError("Moodle username and password are required")
        encrypted_username = self._cipher.encrypt(username)
        encrypted_password = self._cipher.encrypt(password)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE users
                SET moodle_username_encrypted = ?, moodle_password_encrypted = ?,
                    updated_at = ?
                WHERE id = ? AND enabled = 1
                """,
                (encrypted_username, encrypted_password, int(time.time()), user_id),
            )
        if cursor.rowcount != 1:
            raise AccountNotFound("Enabled account was not found")

    def get_credentials(self, user_id: str) -> tuple[str, str]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT moodle_username_encrypted, moodle_password_encrypted
                FROM users WHERE id = ? AND enabled = 1
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            raise AccountNotFound("Enabled account was not found")
        if (
            row["moodle_username_encrypted"] is None
            or row["moodle_password_encrypted"] is None
        ):
            raise CredentialsNotConfigured("Moodle credentials are not configured")
        return (
            self._cipher.decrypt(row["moodle_username_encrypted"]),
            self._cipher.decrypt(row["moodle_password_encrypted"]),
        )

    @staticmethod
    def _hash_setup_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_setup_token(self, user_id: str, ttl_seconds: int) -> str:
        if ttl_seconds < 60 or ttl_seconds > 3600:
            raise ValueError("Setup token lifetime must be between 60 and 3600 seconds")
        account = self.get_by_local_id(user_id)
        if account is None or not account.enabled:
            raise AccountNotFound("Enabled account was not found")

        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM setup_tokens WHERE expires_at < ? OR user_id = ?",
                (now, user_id),
            )
            connection.execute(
                """
                INSERT INTO setup_tokens (token_hash, user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (self._hash_setup_token(token), user_id, now + ttl_seconds, now),
            )
        return token

    def account_for_setup_token(self, token: str) -> Account | None:
        now = int(time.time())
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT users.* FROM setup_tokens
                JOIN users ON users.id = setup_tokens.user_id
                WHERE setup_tokens.token_hash = ?
                  AND setup_tokens.expires_at >= ?
                  AND users.enabled = 1
                """,
                (self._hash_setup_token(token), now),
            ).fetchone()
        return self._row_to_account(row) if row else None

    def set_credentials_with_setup_token(
        self, token: str, username: str, password: str
    ) -> Account:
        if not username or not password:
            raise ValueError("Moodle username and password are required")
        encrypted_username = self._cipher.encrypt(username)
        encrypted_password = self._cipher.encrypt(password)
        now = int(time.time())
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT users.* FROM setup_tokens
                JOIN users ON users.id = setup_tokens.user_id
                WHERE setup_tokens.token_hash = ?
                  AND setup_tokens.expires_at >= ?
                  AND users.enabled = 1
                """,
                (self._hash_setup_token(token), now),
            ).fetchone()
            if row is None:
                raise InvalidSetupToken("Setup link is invalid or expired")
            account = self._row_to_account(row)
            connection.execute(
                """
                UPDATE users
                SET moodle_username_encrypted = ?, moodle_password_encrypted = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (encrypted_username, encrypted_password, now, account.id),
            )
            connection.execute(
                "DELETE FROM setup_tokens WHERE user_id = ?", (account.id,)
            )
        updated = self.get_by_local_id(account.id)
        if updated is None:
            raise AccountError("Account disappeared while saving credentials")
        return updated


_store: AccountStore | None = None
_store_lock = threading.Lock()


def get_account_store() -> AccountStore:
    global _store
    if _store is not None:
        return _store

    from config import CREDENTIAL_ENCRYPTION_KEY, DATABASE_PATH

    if not CREDENTIAL_ENCRYPTION_KEY:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY is required")
    with _store_lock:
        if _store is None:
            _store = AccountStore(DATABASE_PATH, CREDENTIAL_ENCRYPTION_KEY)
    return _store
