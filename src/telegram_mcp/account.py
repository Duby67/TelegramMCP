"""Interactive login and exclusive ownership of a persistent Telegram session."""

import fcntl
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from getpass import getpass

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from telegram_mcp.config import Settings


class AccountError(RuntimeError):
    """An operator-facing account error without credentials or Telegram responses."""


def create_client(settings: Settings) -> TelegramClient:
    logger = logging.getLogger("telegram_mcp.transport")
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False
    return TelegramClient(
        str(settings.session_path),
        settings.api_id,
        settings.api_hash,
        request_retries=0,
        connection_retries=1,
        flood_sleep_threshold=0,
        raise_last_call_error=True,
        receive_updates=False,
        base_logger=logger,
    )


@asynccontextmanager
async def connected_client(
    settings: Settings, *, require_authorized: bool = True
) -> AsyncIterator[TelegramClient]:
    os.umask(0o077)
    if require_authorized and not settings.session_path.is_file():
        raise AccountError("No Telegram session. Run 'telegram-mcp auth' first.")
    settings.session_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = settings.session_dir / "telegram.lock"
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AccountError(
                "Telegram session is already in use. Stop the other service or auth command."
            ) from None
        try:
            client = create_client(settings)
        except Exception:
            raise AccountError(
                "Cannot open Telegram session. Check storage permissions and session integrity."
            ) from None
        try:
            settings.session_path.chmod(0o600)
            try:
                await client.connect()
                authorized = await client.is_user_authorized()
            except Exception:
                raise AccountError(
                    "Cannot connect to Telegram. Check credentials, network, and session storage."
                ) from None
            if require_authorized and not authorized:
                raise AccountError("Telegram session expired. Run 'telegram-mcp auth' again.")
            yield client
        finally:
            try:
                await client.disconnect()
            except Exception:
                raise AccountError(
                    "Cannot close Telegram session cleanly. Stop the process before restarting."
                ) from None


async def authorize(settings: Settings) -> None:
    async with connected_client(settings, require_authorized=False) as client:
        try:
            if await client.is_user_authorized():
                print("Telegram session is already authorized.")
                return
            phone = input("Telegram phone number (international format): ").strip()
            sent = await client.send_code_request(phone)
            code = getpass("Telegram login code (hidden): ").strip()
            try:
                await client.sign_in(phone, code, phone_code_hash=sent.phone_code_hash)
            except SessionPasswordNeededError:
                await client.sign_in(password=getpass("Telegram 2FA password (hidden): "))
        except Exception:
            raise AccountError(
                "Telegram login failed. Check your credentials and code, then run auth again."
            ) from None
        print("Telegram session saved. You can now start the MCP service.")
