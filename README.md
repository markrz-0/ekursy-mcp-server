# eKursy MCP Server

A remote Model Context Protocol server that exposes a student's eKursy profile,
courses, grades, forums, and course materials. It uses FastMCP over Streamable
HTTP, the bundled `ekursy-zero` Rust service, and invite-only GitHub OAuth.

Each GitHub identity maps to its own Moodle credentials in SQLite. Credential
fields are encrypted with Fernet authenticated encryption before being written
to disk. OAuth tokens and MCP tool calls never contain the university password.

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
4. Copy `.env.example` to `.env`, fill the GitHub client ID/secret, and
   independently generate both
   `OAUTH_JWT_SIGNING_KEY` and `CREDENTIAL_ENCRYPTION_KEY` with
   `openssl rand -hex 32`.
5. Keep `.env` mode `600` on the server.

`OAUTH_ALLOWED_GITHUB_USERS` is only a bootstrap list. On that user's next
authenticated request, the server records their immutable numeric GitHub ID
with no Moodle credentials. New users must be invited with the admin command
below.

Never rotate `CREDENTIAL_ENCRYPTION_KEY` while the SQLite database contains
credentials. Losing it makes those credential records unrecoverable.

## Deploy

```bash
git submodule update --init --recursive
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 ekursy-mcp
```

The SQLite account database, OAuth state, and downloaded course files use named
Docker volumes, so they survive container recreation and are not stored in the
Git checkout.

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
authorization as an invited account. Then install the resulting plugin and use
it from the conversation in which you create the scheduled task.

The first account listed in `OAUTH_ALLOWED_GITHUB_USERS` is bootstrapped on its
next request. Ask the connector to run `create_account_setup_link`, open the
returned browser link, and enter your Moodle credentials there.

## Add a friend

Invite their GitHub account from the VPS. The command resolves the login to
GitHub's immutable numeric user ID before storing it:

```bash
cd /home/saell/ekursy-mcp
docker compose exec ekursy-mcp /app/.venv/bin/python src/admin.py invite THEIR_GITHUB_LOGIN
docker compose exec ekursy-mcp /app/.venv/bin/python src/admin.py list
```

Your friend then adds `https://mk.uni.markrz0.dev/mcp` in ChatGPT and completes
GitHub OAuth. In ChatGPT they ask the connector to run
`create_account_setup_link`, open the returned short-lived one-time link in a
browser, and enter their own Moodle credentials. The server validates and
encrypts them directly; they do not pass through ChatGPT.

Disable or re-enable access without deleting the encrypted record:

```bash
docker compose exec ekursy-mcp /app/.venv/bin/python src/admin.py disable THEIR_GITHUB_LOGIN
docker compose exec ekursy-mcp /app/.venv/bin/python src/admin.py enable THEIR_GITHUB_LOGIN
```

Each Moodle login has an isolated server-side session. Tool calls resolve the
authenticated GitHub ID to exactly one database record before accessing Moodle.

The exact availability of custom MCP servers and scheduled tasks depends on
your ChatGPT plan and workspace policy.

## Local development

Initialize the scraper submodule, copy `.env.example` to `.env`, configure the
OAuth settings, and install dependencies with `uv`:

```bash
git submodule update --init --recursive
uv sync --frozen
docker compose up --build
```

Run tests with:

```bash
python -m unittest discover -s tests -v
```
