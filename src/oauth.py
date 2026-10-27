from __future__ import annotations

import logging
from typing import Any

import httpx
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.github import GitHubProvider

logger = logging.getLogger(__name__)


def github_login_is_allowed(
    token: AccessToken | None, allowed_logins: set[str]
) -> bool:
    """Return True only for a GitHub identity explicitly allowlisted by login."""
    if token is None:
        return False
    upstream_claims = token.claims.get("upstream_claims", {})
    login = upstream_claims.get("login")
    return isinstance(login, str) and login.lower() in allowed_logins


class AllowlistedGitHubProvider(GitHubProvider):
    """GitHub OAuth proxy that limits access to explicitly configured users."""

    def __init__(self, *, allowed_logins: set[str], **kwargs: Any) -> None:
        if not allowed_logins:
            raise ValueError("At least one allowed GitHub login is required")
        self.allowed_logins = {login.lower() for login in allowed_logins}
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
        if not github_login_is_allowed(verified, self.allowed_logins):
            logger.warning("Rejected an OAuth token for a non-allowlisted GitHub user")
            return None
        return verified
