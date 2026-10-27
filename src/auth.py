from __future__ import annotations

import asyncio
from collections import defaultdict

import httpx

from accounts import CredentialsNotConfigured, get_account_store
from config import API_BASE_URL


_active_session_keys: dict[str, str] = {}
_session_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def login_to_moodle(client: httpx.AsyncClient, user_id: str) -> str:
    username, password = get_account_store().get_credentials(user_id)
    response = await client.post(
        f"{API_BASE_URL}/api/login",
        json={"email": username, "password": password},
    )

    if not response.is_success:
        try:
            err_data = response.json()
            error_code = err_data.get("error", "AUTH_ERR")
            message = err_data.get("msg", "Unknown authentication error")
        except Exception:
            error_code = "AUTH_ERR"
            message = "Unknown authentication error"
        raise RuntimeError(f"[{error_code}] {message}")

    data = response.json()
    session_key = data.get("moodleSessionKey")
    if not isinstance(session_key, str) or not session_key:
        raise RuntimeError("Moodle login did not return a session key")
    _active_session_keys[user_id] = session_key
    return session_key


async def _get_or_create_session(client: httpx.AsyncClient, user_id: str) -> str:
    session_key = _active_session_keys.get(user_id)
    if session_key:
        return session_key
    async with _session_locks[user_id]:
        session_key = _active_session_keys.get(user_id)
        if session_key:
            return session_key
        return await login_to_moodle(client, user_id)


def invalidate_moodle_session(user_id: str) -> None:
    _active_session_keys.pop(user_id, None)


async def validate_moodle_credentials(username: str, password: str) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{API_BASE_URL}/api/login",
            json={"email": username, "password": password},
        )
    if not response.is_success:
        raise CredentialsNotConfigured("Moodle rejected these credentials")
    data = response.json()
    if not data.get("moodleSessionKey"):
        raise CredentialsNotConfigured("Moodle did not return a session key")


async def fetch_with_auth(
    client: httpx.AsyncClient, user_id: str, endpoint: str, **kwargs
) -> httpx.Response:
    session_key = await _get_or_create_session(client, user_id)
    headers = dict(kwargs.pop("headers", {}))
    headers["Authorization"] = session_key

    async def make_request() -> httpx.Response:
        return await client.get(
            f"{API_BASE_URL}{endpoint}", headers=headers, **kwargs
        )

    response = await make_request()
    if response.status_code == 401:
        async with _session_locks[user_id]:
            invalidate_moodle_session(user_id)
            headers["Authorization"] = await login_to_moodle(client, user_id)
        response = await make_request()
    return response
