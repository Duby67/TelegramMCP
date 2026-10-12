"""Operator commands; account credentials are never command-line arguments."""

import argparse
import asyncio
import json
import sys
import threading

from telegram_mcp.account import AccountError, authorize, connected_client
from telegram_mcp.config import ConfigurationError, Settings
from telegram_mcp.models import dialog_from_telegram
from telegram_mcp.server import serve


async def show_dialogs(settings: Settings) -> None:
    """Owner-only discovery; this command is not exposed as an MCP tool."""
    async with connected_client(settings) as client:
        try:
            async for dialog in client.iter_dialogs():
                model = dialog_from_telegram(dialog)
                print(
                    json.dumps(
                        {"dialog_id": model.dialog_id, "title": model.title, "kind": model.kind},
                        ensure_ascii=False,
                    )
                )
        except Exception:
            raise AccountError(
                "Cannot list dialogs. Check Telegram connectivity and access."
            ) from None


def main() -> None:
    parser = argparse.ArgumentParser(prog="telegram-mcp")
    parser.add_argument("--version", action="version", version="telegram-mcp 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("auth", help="Authorize Telegram interactively and save the session")
    commands.add_parser("dialogs", help="Show dialog metadata locally (optional owner diagnostic)")
    commands.add_parser("serve", help="Start the Streamable HTTP MCP service")
    args = parser.parse_args()
    try:
        if args.command == "auth":
            asyncio.run(authorize(Settings.from_env()))
        elif args.command == "dialogs":
            asyncio.run(show_dialogs(Settings.from_env()))
        elif args.command == "serve":
            try:
                settings = Settings.from_env()
                settings.validate_http()
            except ConfigurationError as exc:
                # Stay up so a container restart policy does not loop on a static error.
                print(f"{exc} Fix the environment and recreate the service.", file=sys.stderr)
                threading.Event().wait()
            serve(settings)
    except (ConfigurationError, AccountError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except OSError:
        print(
            "Cannot access session storage. Check its ownership and permissions.", file=sys.stderr
        )
        raise SystemExit(1) from None
    except (KeyboardInterrupt, EOFError):
        print("Cancelled.", file=sys.stderr)
        raise SystemExit(1) from None
