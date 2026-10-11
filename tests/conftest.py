from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telethon import types

from telegram_mcp.access import AccessPolicy
from telegram_mcp.config import Settings
from telegram_mcp.service import TelegramService

NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
CHANNEL_ID = "-1000000000040"


def make_message(message_id: int, text: str = "test") -> types.Message:
    return types.Message(
        id=message_id,
        peer_id=types.PeerUser(10),
        from_id=types.PeerUser(20),
        date=NOW + timedelta(minutes=message_id),
        message=text,
    )


def make_dialog(dialog_id: str, kind: str, **entity_fields) -> SimpleNamespace:
    return SimpleNamespace(
        id=int(dialog_id),
        name=f"test-{kind}",
        is_group=kind == "group",
        is_channel=kind != "private",
        entity=SimpleNamespace(**entity_fields),
    )


class FakeClient:
    def __init__(self):
        self.dialogs = [
            make_dialog("10", "private"),
            make_dialog("-30", "group"),
            make_dialog(CHANNEL_ID, "channel"),
            make_dialog("99", "private"),
        ]
        self.messages = [make_message(i) for i in (5, 4, 3, 2, 1)]
        self.get_input_entity = AsyncMock(side_effect=lambda value: value)
        self.get_messages = AsyncMock(return_value=make_message(1))
        self.send_message = AsyncMock(return_value=make_message(6))

    async def iter_dialogs(self):
        for dialog in self.dialogs:
            yield dialog

    async def iter_messages(self, peer, *, limit, offset_id, offset_date):
        for message in self.messages:
            if offset_id and message.id >= offset_id:
                continue
            if offset_date is not None and message.date >= offset_date:
                continue
            yield message


@pytest.fixture
def fake_client():
    return FakeClient()


@pytest.fixture
def service(fake_client):
    return TelegramService(
        fake_client,
        AccessPolicy(frozenset({"10", "-30", CHANNEL_ID}), frozenset({"10", CHANNEL_ID})),
    )


@pytest.fixture
def settings(tmp_path: Path):
    return Settings(api_id=1, api_hash="0" * 32, session_dir=tmp_path / "data")
