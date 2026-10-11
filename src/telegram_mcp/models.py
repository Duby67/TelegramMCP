"""Shared result contracts for private chats, groups, and channels."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from telethon import utils

DialogKind = Literal["private", "group", "channel"]


class Result(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Dialog(Result):
    dialog_id: str
    title: str
    kind: DialogKind
    username: str | None = None
    telegram_send_capability: Literal["allowed", "restricted", "unknown"] = "unknown"
    read_allowed: bool = False
    write_allowed: bool = False


class Message(Result):
    dialog_id: str
    message_id: int
    date: datetime
    sender_id: str | None = None
    text: str
    reply_to_message_id: int | None = None
    has_media: bool = False


class DialogPage(Result):
    dialogs: list[Dialog]
    next_cursor: str | None = None


class MessagePage(Result):
    messages: list[Message]
    next_before_id: int | None = None


class SendResult(Result):
    message: Message
    status: Literal["sent"] = "sent"


class ErrorDetail(Result):
    code: str
    message: str
    retry_after_seconds: int | None = None
    delivery_status: Literal["not_attempted", "rejected", "unknown"] | None = None


class ErrorResult(Result):
    error: ErrorDetail


def validate_dialog_id(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise ValueError("dialog_id must be a signed decimal ID from list_dialogs.") from None
    if parsed == 0 or str(parsed) != value or not -(2**63) <= parsed < 2**63:
        raise ValueError("dialog_id must be a nonzero canonical signed 64-bit decimal ID.")
    return parsed


def dialog_from_telegram(dialog: Any) -> Dialog:
    entity = dialog.entity
    kind: DialogKind = "private"
    if dialog.is_group:
        kind = "group"
    elif dialog.is_channel:
        kind = "channel"
    capability: Literal["allowed", "restricted", "unknown"] = "unknown"
    if kind == "channel":
        rights = getattr(entity, "admin_rights", None)
        capability = (
            "allowed"
            if getattr(entity, "creator", False) or getattr(rights, "post_messages", False)
            else "restricted"
        )
    return Dialog(
        dialog_id=str(dialog.id),
        title=dialog.name or "",
        kind=kind,
        username=getattr(entity, "username", None),
        telegram_send_capability=capability,
    )


def message_from_telegram(dialog_id: str, message: Any) -> Message:
    sender = getattr(message, "from_id", None)
    return Message(
        dialog_id=dialog_id,
        message_id=message.id,
        date=message.date,
        sender_id=str(utils.get_peer_id(sender)) if sender is not None else None,
        text=message.message or "",
        reply_to_message_id=getattr(message, "reply_to_msg_id", None),
        has_media=getattr(message, "media", None) is not None,
    )
