import os
import sys
from urllib.parse import urlsplit

# Environment Configuration
USERNAME = os.environ.get("MOODLE_USERNAME")
PASSWORD = os.environ.get("MOODLE_PASSWORD")
PORT = int(os.environ.get('PORT', '6969'))
API_BASE_URL = os.environ.get("MOODLE_API_BASE", "http://moodle-api:8080")
TIMEOUT = float(os.environ.get("MOODLE_TIMEOUT", "30.0"))
DATABASE_PATH = os.environ.get("DATABASE_PATH", "/app/data/ekursy.db")
CREDENTIAL_ENCRYPTION_KEY = os.environ.get("CREDENTIAL_ENCRYPTION_KEY")
ACCOUNT_SETUP_TOKEN_TTL = int(os.environ.get("ACCOUNT_SETUP_TOKEN_TTL", "600"))
MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio")
MCP_AUTH_PROVIDER = os.environ.get("MCP_AUTH_PROVIDER", "none").lower()
MCP_PUBLIC_URL = os.environ.get("MCP_PUBLIC_URL", "").rstrip("/")

OAUTH_GITHUB_CLIENT_ID = os.environ.get("OAUTH_GITHUB_CLIENT_ID")
OAUTH_GITHUB_CLIENT_SECRET = os.environ.get("OAUTH_GITHUB_CLIENT_SECRET")
OAUTH_JWT_SIGNING_KEY = os.environ.get("OAUTH_JWT_SIGNING_KEY")
OAUTH_ALLOWED_GITHUB_USERS = {
    user.strip().lower()
    for user in os.environ.get("OAUTH_ALLOWED_GITHUB_USERS", "").split(",")
    if user.strip()
}
OAUTH_ALLOWED_REDIRECT_URIS = [
    uri.strip()
    for uri in os.environ.get(
        "OAUTH_ALLOWED_REDIRECT_URIS",
        (
            "https://chatgpt.com/connector_platform_oauth_redirect,"
            "https://chatgpt.com/connector/oauth/*,"
            "http://127.0.0.1:*/callback"
        ),
    ).split(",")
    if uri.strip()
]

if MCP_AUTH_PROVIDER not in {"none", "github"}:
    print("CRITICAL ERROR: MCP_AUTH_PROVIDER must be 'none' or 'github'.", file=sys.stderr)
    sys.exit(1)

if MCP_TRANSPORT == "streamable-http" and MCP_AUTH_PROVIDER != "github":
    print(
        "CRITICAL ERROR: Remote streamable-http mode requires MCP_AUTH_PROVIDER=github.",
        file=sys.stderr,
    )
    sys.exit(1)

if MCP_AUTH_PROVIDER == "github":
    required_oauth_values = {
        "MCP_PUBLIC_URL": MCP_PUBLIC_URL,
        "OAUTH_GITHUB_CLIENT_ID": OAUTH_GITHUB_CLIENT_ID,
        "OAUTH_GITHUB_CLIENT_SECRET": OAUTH_GITHUB_CLIENT_SECRET,
        "OAUTH_JWT_SIGNING_KEY": OAUTH_JWT_SIGNING_KEY,
        "CREDENTIAL_ENCRYPTION_KEY": CREDENTIAL_ENCRYPTION_KEY,
    }
    missing = [name for name, value in required_oauth_values.items() if not value]
    if missing:
        print(
            f"CRITICAL ERROR: Missing OAuth configuration: {', '.join(missing)}.",
            file=sys.stderr,
        )
        sys.exit(1)

if MCP_AUTH_PROVIDER == "none" and (not USERNAME or not PASSWORD):
    print(
        "CRITICAL ERROR: Local no-auth mode requires MOODLE_USERNAME and MOODLE_PASSWORD.",
        file=sys.stderr,
    )
    sys.exit(1)

if MCP_AUTH_PROVIDER == "github":
    parsed_public_url = urlsplit(MCP_PUBLIC_URL)
    if parsed_public_url.scheme != "https" or not parsed_public_url.netloc:
        print("CRITICAL ERROR: MCP_PUBLIC_URL must be an HTTPS origin.", file=sys.stderr)
        sys.exit(1)
    if parsed_public_url.path not in {"", "/"}:
        print(
            "CRITICAL ERROR: MCP_PUBLIC_URL must not include /mcp or another path.",
            file=sys.stderr,
        )
        sys.exit(1)

