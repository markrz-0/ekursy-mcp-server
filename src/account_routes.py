from __future__ import annotations

import html
import logging

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from accounts import CredentialsNotConfigured, InvalidSetupToken, get_account_store
from auth import invalidate_moodle_session, validate_moodle_credentials
from server import mcp


SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; "
        "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    ),
}
logger = logging.getLogger(__name__)


def _page(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font: 16px system-ui, sans-serif; max-width: 34rem; margin: 4rem auto;
           padding: 0 1rem; color: #17202a; }}
    label {{ display: block; margin-top: 1rem; font-weight: 600; }}
    input {{ box-sizing: border-box; width: 100%; padding: .7rem; margin-top: .35rem; }}
    button {{ margin-top: 1.25rem; padding: .7rem 1rem; cursor: pointer; }}
    .error {{ color: #a40000; }}
    .muted {{ color: #52606d; }}
  </style>
</head>
<body>{body}</body>
</html>"""
    return HTMLResponse(document, status_code=status_code, headers=SECURITY_HEADERS)


def _setup_form(token: str, github_login: str, error: str | None = None) -> str:
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return f"""
<h1>Connect your eKursy account</h1>
<p>GitHub account: <strong>{html.escape(github_login)}</strong></p>
<p class="muted">Your Moodle credentials are sent directly to this server,
validated once, and stored encrypted. They are never sent through ChatGPT.</p>
{error_html}
<form method="post" action="/account/setup" autocomplete="off">
  <input type="hidden" name="token" value="{html.escape(token, quote=True)}">
  <label for="username">University email</label>
  <input id="username" name="username" type="email" required maxlength="254"
         autocomplete="username">
  <label for="password">Moodle password</label>
  <input id="password" name="password" type="password" required maxlength="512"
         autocomplete="current-password">
  <button type="submit">Validate and save</button>
</form>"""


@mcp.custom_route("/account/setup", methods=["GET", "POST"])
async def account_setup(request: Request) -> Response:
    if request.method == "GET":
        token = request.query_params.get("token", "")
        account = get_account_store().account_for_setup_token(token) if token else None
        if account is None:
            return _page(
                "Invalid setup link",
                "<h1>Invalid or expired setup link</h1>"
                "<p>Return to ChatGPT and request a new account setup link.</p>",
                status_code=400,
            )
        return _page(
            "Connect eKursy",
            _setup_form(token, account.github_login),
        )

    try:
        content_length = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        return _page("Invalid request", "<h1>Invalid request</h1>", 400)
    if content_length > 16_384:
        return _page("Request too large", "<h1>Request too large</h1>", 413)

    form = await request.form()
    token = str(form.get("token", ""))
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    account = get_account_store().account_for_setup_token(token) if token else None
    if account is None:
        return _page(
            "Invalid setup link",
            "<h1>Invalid or expired setup link</h1>"
            "<p>Return to ChatGPT and request a new account setup link.</p>",
            status_code=400,
        )
    if not username or not password:
        return _page(
            "Connect eKursy",
            _setup_form(token, account.github_login, "Both fields are required."),
            status_code=400,
        )

    try:
        await validate_moodle_credentials(username, password)
        updated = get_account_store().set_credentials_with_setup_token(
            token, username, password
        )
        invalidate_moodle_session(updated.id)
    except InvalidSetupToken:
        return _page(
            "Invalid setup link",
            "<h1>Invalid or expired setup link</h1>",
            status_code=400,
        )
    except CredentialsNotConfigured:
        return _page(
            "Connect eKursy",
            _setup_form(
                token,
                account.github_login,
                "The university rejected those credentials. Check them and try again.",
            ),
            status_code=400,
        )
    except Exception:
        logger.exception("Failed to save Moodle credentials")
        return _page(
            "Server error",
            "<h1>Could not save credentials</h1>"
            "<p>Please request a new setup link and try again.</p>",
            status_code=500,
        )

    return _page(
        "eKursy connected",
        "<h1>Account connected</h1>"
        "<p>You can close this tab and return to ChatGPT.</p>",
    )
