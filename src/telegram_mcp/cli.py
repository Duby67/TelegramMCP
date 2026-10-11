"""Operator commands; account credentials are never command-line arguments."""

import argparse
import asyncio
import sys

from telegram_mcp.account import AccountError, authorize
from telegram_mcp.config import ConfigurationError, Settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="telegram-mcp")
    parser.add_argument("--version", action="version", version="telegram-mcp 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("auth", help="Authorize Telegram interactively and save the session")
    args = parser.parse_args()
    try:
        if args.command == "auth":
            asyncio.run(authorize(Settings.from_env()))
    except (ConfigurationError, AccountError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except OSError:
        print(
            "Cannot access session storage. Check its ownership and permissions.", file=sys.stderr
        )
        raise SystemExit(1) from None
    except (KeyboardInterrupt, EOFError):
        print("Authorization cancelled.", file=sys.stderr)
        raise SystemExit(1) from None
