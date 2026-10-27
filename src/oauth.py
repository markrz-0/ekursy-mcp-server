from __future__ import annotations

import logging
from typing import Any

import httpx
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.github import GitHubProvider

from accounts import AccountStore

logger = logging.getLogger(__name__)


class AllowlistedGitHubProvider(GitHubProvider):
    """GitHub OAuth proxy backed by an invite-only account database."""

    def __init__(
        self,
        *,
        account_store: AccountStore,
        bootstrap_logins: set[str],
        bootstrap_credentials: tuple[str, str] | None,
        **kwargs: Any,
    ) -> None:
        self.account_store = account_store
        self.bootstrap_logins = {login.lower() for login in bootstrap_logins}
        self.bootstrap_credentials = bootstrap_credentials
        super().__init__(**kwargs)

    async def _extract_upstream_claims(
        self, idp_tokens: dict[str, Any]
    ) -> dict[str, Any] | None:
        access_token = idp_tokens.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            return None

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github+json",
                        "User-Agent": "ekursy-mcp-server",
                    },
                )
                response.raise_for_status()
                user = response.json()
        except (httpx.HTTPError, ValueError):
            logger.warning("Unable to resolve the GitHub identity during OAuth")
            return None

        return {
            "sub": str(user.get("id", "")),
            "login": user.get("login"),
        }

    async def verify_token(self, token: str) -> AccessToken | None:
        verified = await super().verify_token(token)
        if verified is None:
            return None
        upstream_claims = verified.claims.get("upstream_claims", {})
        github_user_id = upstream_claims.get("sub")
        github_login = upstream_claims.get("login")
        if not isinstance(github_user_id, str) or not isinstance(github_login, str):
            logger.warning("Rejected an OAuth token without a stable GitHub identity")
            return None
        if not self.account_store.authorize_identity(
            github_user_id,
            github_login,
            self.bootstrap_logins,
            self.bootstrap_credentials,
        ):
            logger.warning("Rejected OAuth for a GitHub user who was not invited")
            return None
        return verified
