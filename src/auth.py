import httpx
from config import USERNAME, PASSWORD, API_BASE_URL

# In-Memory Session State
active_session_key: str | None = None

# 1. Authentication Engine
async def login_to_moodle(client: httpx.AsyncClient) -> str:
    global active_session_key
    response = await client.post(
        f"{API_BASE_URL}/api/login",
        json={"email": USERNAME, "password": PASSWORD}
    )

    if not response.is_success:
        try:
            err_data = response.json()
            error_code = err_data.get("error", "AUTH_ERR")
            msg = err_data.get("msg", "Unknown authentication error")
        except Exception:
            error_code = "AUTH_ERR"
            msg = "Unknown authentication error"
        raise Exception(f"[{error_code}] {msg}")

    data = response.json()
    active_session_key = data.get("moodleSessionKey")
    return active_session_key

# 2. Authenticated Fetch Helper (Handles 401 Auto-Recovery)
async def fetch_with_auth(client: httpx.AsyncClient, endpoint: str, **kwargs) -> httpx.Response:
    global active_session_key
    if not active_session_key:
        await login_to_moodle(client)

    headers = kwargs.pop("headers", {})
    headers["Authorization"] = active_session_key

    # Manual request helper
    async def make_request():
        return await client.get(f"{API_BASE_URL}{endpoint}", headers=headers, **kwargs)

    response = await make_request()

    # Desync Recovery: Re-login and retry once if the session expired
    if response.status_code == 401:
        await login_to_moodle(client)
        headers["Authorization"] = active_session_key
        response = await make_request()

    return response
