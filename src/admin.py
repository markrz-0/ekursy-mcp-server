from __future__ import annotations

import argparse
import sys

import httpx

from accounts import Account, get_account_store


def resolve_github_user(login: str) -> tuple[str, str]:
    response = httpx.get(
        f"https://api.github.com/users/{login}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ekursy-mcp-admin",
        },
        timeout=10,
        follow_redirects=True,
    )
    if response.status_code == 404:
        raise RuntimeError(f"GitHub user {login!r} was not found")
    response.raise_for_status()
    user = response.json()
    github_id = user.get("id")
    canonical_login = user.get("login")
    if not isinstance(github_id, int) or not isinstance(canonical_login, str):
        raise RuntimeError("GitHub returned an invalid user record")
    return str(github_id), canonical_login


def format_account(account: Account) -> str:
    status = "enabled" if account.enabled else "disabled"
    credentials = "configured" if account.has_credentials else "not configured"
    return (
        f"{account.github_login}\tgithub_id={account.github_user_id}\t"
        f"{status}\tcredentials={credentials}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage invited eKursy MCP users")
    subparsers = parser.add_subparsers(dest="command", required=True)
    invite = subparsers.add_parser("invite", help="Invite a GitHub account")
    invite.add_argument("github_login")
    subparsers.add_parser("list", help="List accounts")
    for command in ("enable", "disable"):
        item = subparsers.add_parser(command, help=f"{command.title()} an account")
        item.add_argument("github_login")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    store = get_account_store()
    if args.command == "list":
        for account in store.list_accounts():
            print(format_account(account))
        return 0

    github_id, canonical_login = resolve_github_user(args.github_login)
    if args.command == "invite":
        print(format_account(store.invite(github_id, canonical_login)))
        return 0

    enabled = args.command == "enable"
    if not store.set_enabled(github_id, enabled):
        raise RuntimeError(
            f"{canonical_login!r} is not in the account database; invite them first"
        )
    account = store.get_by_github_id(github_id)
    if account is None:
        raise RuntimeError("Account disappeared after update")
    print(format_account(account))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
