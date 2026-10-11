"""Telegram operations independent of MCP transport."""

from datetime import datetime

from telethon import TelegramClient

from telegram_mcp.models import (
    DialogPage,
    MessagePage,
    SendResult,
    dialog_from_telegram,
    message_from_telegram,
    validate_dialog_id,
)


def validate_limit(limit: int) -> None:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100.")


class TelegramService:
    def __init__(self, client: TelegramClient) -> None:
        self.client = client

    async def list_dialogs(self, limit: int = 50, cursor: str | None = None) -> DialogPage:
        validate_limit(limit)
        after_id = validate_dialog_id(cursor) if cursor is not None else None
        dialogs = [dialog_from_telegram(d) async for d in self.client.iter_dialogs()]
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
        numeric_id = validate_dialog_id(dialog_id)
        if before_id is not None and before_id <= 0:
            raise ValueError("before_id must be positive.")
        for bound in (since, until):
            if bound is not None and (bound.tzinfo is None or bound.utcoffset() is None):
                raise ValueError("Time filters must include a timezone.")
        if since is not None and until is not None and since >= until:
            raise ValueError("since must be earlier than until.")
        peer = await self.client.get_input_entity(numeric_id)
        messages = []
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
        numeric_id = validate_dialog_id(dialog_id)
        if not text.strip() or len(text.encode("utf-16-le")) // 2 > 4096:
            raise ValueError("text must contain 1–4096 UTF-16 code units of nonblank text.")
        if reply_to_message_id is not None and reply_to_message_id <= 0:
            raise ValueError("reply_to_message_id must be positive.")
        peer = await self.client.get_input_entity(numeric_id)
        if reply_to_message_id is not None:
            replied = await self.client.get_messages(peer, ids=reply_to_message_id)
            if replied is None:
                raise ValueError("The reply target does not exist in this dialog.")
        message = await self.client.send_message(
            peer,
            text,
            reply_to=reply_to_message_id,
            parse_mode=None,
            link_preview=False,
        )
        return SendResult(message=message_from_telegram(dialog_id, message))
