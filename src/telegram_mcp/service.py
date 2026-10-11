"""Telegram operations independent of MCP transport."""

import asyncio
from datetime import datetime

from telethon import TelegramClient

from telegram_mcp.access import AccessPolicy
from telegram_mcp.errors import invalid_request, telegram_errors
from telegram_mcp.models import (
    DialogPage,
    MessagePage,
    SendResult,
    dialog_from_telegram,
    message_from_telegram,
    validate_dialog_id,
)

REQUEST_TIMEOUT_SECONDS = 30


def validate_limit(limit: int) -> None:
    if not 1 <= limit <= 100:
        raise invalid_request("limit must be between 1 and 100.")


class TelegramService:
    def __init__(self, client: TelegramClient, policy: AccessPolicy) -> None:
        self.client = client
        self.policy = policy

    async def list_dialogs(self, limit: int = 50, cursor: str | None = None) -> DialogPage:
        validate_limit(limit)
        with telegram_errors():
            after_id = validate_dialog_id(cursor) if cursor is not None else None
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                dialogs = [
                    self.policy.annotate(dialog_from_telegram(d))
                    async for d in self.client.iter_dialogs()
                    if self.policy.visible(str(d.id))
                ]
        dialogs.sort(key=lambda d: int(d.dialog_id))
        if after_id is not None:
            dialogs = [d for d in dialogs if int(d.dialog_id) > after_id]
        page = dialogs[:limit]
        return DialogPage(
            dialogs=page,
            next_cursor=page[-1].dialog_id if len(dialogs) > limit else None,
        )

    async def get_messages(
        self,
        dialog_id: str,
        limit: int = 50,
        before_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> MessagePage:
        validate_limit(limit)
        self.policy.require(dialog_id, "read")
        with telegram_errors():
            numeric_id = validate_dialog_id(dialog_id)
        if before_id is not None and before_id <= 0:
            raise invalid_request("before_id must be positive.")
        for bound in (since, until):
            if bound is not None and (bound.tzinfo is None or bound.utcoffset() is None):
                raise invalid_request("Time filters must include a timezone.")
        if since is not None and until is not None and since >= until:
            raise invalid_request("since must be earlier than until.")
        messages = []
        with telegram_errors():
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                peer = await self.client.get_input_entity(numeric_id)
                async for message in self.client.iter_messages(
                    peer, limit=None, offset_id=before_id or 0, offset_date=until
                ):
                    if since is not None and message.date < since:
                        break
                    if until is not None and message.date >= until:
                        continue
                    messages.append(message_from_telegram(dialog_id, message))
                    if len(messages) > limit:
                        break
        page = messages[:limit]
        return MessagePage(
            messages=page,
            next_before_id=page[-1].message_id if len(messages) > limit else None,
        )

    async def send_message(
        self, dialog_id: str, text: str, reply_to_message_id: int | None = None
    ) -> SendResult:
        self.policy.require(dialog_id, "write")
        with telegram_errors(sending=True):
            numeric_id = validate_dialog_id(dialog_id)
            text_size = len(text.encode("utf-16-le")) // 2
        if not text.strip() or text_size > 4096:
            raise invalid_request(
                "text must contain 1–4096 UTF-16 code units of nonblank text.", sending=True
            )
        if reply_to_message_id is not None and reply_to_message_id <= 0:
            raise invalid_request("reply_to_message_id must be positive.", sending=True)
        with telegram_errors(sending=True):
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                peer = await self.client.get_input_entity(numeric_id)
                if reply_to_message_id is not None:
                    replied = await self.client.get_messages(peer, ids=reply_to_message_id)
                    if replied is None:
                        raise invalid_request(
                            "The reply target does not exist in this dialog.", sending=True
                        )
        with telegram_errors(sending=True, attempted=True):
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                message = await self.client.send_message(
                    peer,
                    text,
                    reply_to=reply_to_message_id,
                    parse_mode=None,
                    link_preview=False,
                )
                return SendResult(message=message_from_telegram(dialog_id, message))
