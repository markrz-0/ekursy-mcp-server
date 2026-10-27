from __future__ import annotations

from fastmcp.server.auth import AccessToken
from fastmcp.server.dependencies import get_access_token

from accounts import Account, AccountNotFound, get_account_store
from config import MCP_AUTH_PROVIDER


def github_identity_from_token(token: AccessToken | None) -> tuple[str, str] | None:
    if token is None:
        return None
    upstream_claims = token.claims.get("upstream_claims", {})
    github_user_id = upstream_claims.get("sub")
    github_login = upstream_claims.get("login")
    if not isinstance(github_user_id, str) or not github_user_id:
        return None
    if not isinstance(github_login, str) or not github_login:
        return None
    return github_user_id, github_login


def require_current_account() -> Account:
    if MCP_AUTH_PROVIDER == "none":
        return Account(
            id="local",
            github_user_id="local",
            github_login="local",
            enabled=True,
            has_credentials=True,
        )
    identity = github_identity_from_token(get_access_token())
    if identity is None:
        raise AccountNotFound("Authenticated GitHub identity is unavailable")
    account = get_account_store().get_by_github_id(identity[0])
    if account is None or not account.enabled:
        raise AccountNotFound("This GitHub account has not been invited")
    return account
