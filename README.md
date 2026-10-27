# eKursy MCP Server

A remote Model Context Protocol server that exposes a student's eKursy profile,
courses, grades, forums, and course materials. It uses FastMCP over Streamable
HTTP, the bundled `ekursy-zero` Rust service, and GitHub OAuth with an explicit
user allowlist.

The university credentials never leave the server. OAuth tokens authorize MCP
requests but do not contain the university username or password.

## Production endpoint

The production MCP URL is:

```text
https://mk.uni.markrz0.dev/mcp
```

OAuth discovery and callback routes are served on the same origin. The Docker
port is bound only to `127.0.0.1`; nginx is the public TLS endpoint.

---

## Production prerequisites

1. Create a GitHub OAuth app at <https://github.com/settings/developers>.
2. Set its homepage URL to `https://mk.uni.markrz0.dev`.
3. Set its authorization callback URL to
   `https://mk.uni.markrz0.dev/auth/callback`.
4. Copy `.env.example` to `.env`, fill the GitHub client ID/secret and
   university credentials, and generate `OAUTH_JWT_SIGNING_KEY` with
   `openssl rand -hex 32`.
5. Keep `.env` mode `600` on the server.

`OAUTH_ALLOWED_GITHUB_USERS` is the security boundary around the shared
university account. Do not remove the allowlist or add users who should not see
the account data.

## Deploy

```bash
git submodule update --init --recursive
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 ekursy-mcp
```

The OAuth state and downloaded course files use named Docker volumes, so they
survive container recreation and are not stored in the Git checkout.

To install nginx and obtain the certificate on Ubuntu, copy
`deploy/install-nginx.sh` to the VPS and run:

```bash
sudo bash ~/install-ekursy-nginx.sh you@example.com
```

The script validates nginx before every reload and lets Certbot add the TLS and
HTTP-to-HTTPS configuration.

On the prepared VPS deployment, enter the GitHub OAuth credentials without
putting the secret in shell history, start the containers, and then install TLS:

```bash
bash ~/finish-ekursy-deploy.sh
sudo bash ~/install-ekursy-nginx.sh you@example.com
```

## Connect from ChatGPT

Add a custom MCP server/plugin with the server URL
`https://mk.uni.markrz0.dev/mcp` and OAuth authentication. Complete the GitHub
authorization as the allowlisted account. Then install the resulting plugin and
use it from the conversation in which you create the scheduled task.

The exact availability of custom MCP servers and scheduled tasks depends on
your ChatGPT plan and workspace policy.

## Local development

Initialize the scraper submodule and install dependencies with `uv`. For local
stdio use, `.env` only needs `MOODLE_USERNAME` and `MOODLE_PASSWORD`; stdio
defaults to no MCP-layer OAuth:

```bash
git submodule update --init --recursive
uv sync --frozen
uv run src/main.py
```

Example stdio client configuration:

```json
{
  "mcpServers": {
    "ekursy": {
      "command": "uv",
      "args": ["run", "src/main.py"],
      "cwd": "C:\\path\\to\\ekursy-mcp-py",
      "env": {
        "MOODLE_USERNAME": "your.email@student.put.poznan.pl",
        "MOODLE_PASSWORD": "your_moodle_password",
        "MOODLE_API_BASE": "http://localhost:8080"
      }
    }
  }
}
```

Run tests with:

```bash
python -m unittest discover -s tests -v
```
