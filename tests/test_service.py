import asyncio
from datetime import timedelta

import pytest
from telethon import errors, types

from telegram_mcp.access import AccessPolicy
from telegram_mcp.errors import OperationError
from telegram_mcp.models import dialog_from_telegram, message_from_telegram
from telegram_mcp.service import TelegramService

from .conftest import CHANNEL_ID, NOW, make_dialog, make_message


async def test_dialog_pages_filter_before_pagination_and_keep_types(service):
    first = await service.list_dialogs(limit=2)
    second = await service.list_dialogs(limit=2, cursor=first.next_cursor)
    assert [d.dialog_id for d in first.dialogs] == [CHANNEL_ID, "-30"]
    assert [d.kind for d in first.dialogs] == ["channel", "group"]
    assert first.next_cursor == "-30"
    assert [d.dialog_id for d in second.dialogs] == ["10"]
    assert second.next_cursor is None
    assert first.dialogs[0].write_allowed
    assert not first.dialogs[1].write_allowed
    assert all(d.dialog_id != "99" for d in first.dialogs + second.dialogs)


async def test_default_policy_denies_all(fake_client):
    service = TelegramService(fake_client, AccessPolicy(frozenset(), frozenset()))
    assert (await service.list_dialogs()).dialogs == []
    with pytest.raises(OperationError, match="read access"):
        await service.get_messages("10")
    with pytest.raises(OperationError, match="write access") as exc:
        await service.send_message("10", "test")
    assert exc.value.detail.delivery_status == "not_attempted"
    fake_client.get_input_entity.assert_not_called()
    fake_client.send_message.assert_not_called()


async def test_write_permission_does_not_grant_read(fake_client):
    service = TelegramService(fake_client, AccessPolicy(frozenset(), frozenset({"10"})))
    assert not (await service.list_dialogs()).dialogs[0].read_allowed
    with pytest.raises(OperationError):
        await service.get_messages("10")
    await service.send_message("10", "test")
    fake_client.send_message.assert_awaited_once()


async def test_message_pagination_has_no_overlap(service):
    first = await service.get_messages("10", limit=2)
    second = await service.get_messages("10", limit=2, before_id=first.next_before_id)
    third = await service.get_messages("10", limit=2, before_id=second.next_before_id)
    assert [[m.message_id for m in p.messages] for p in (first, second, third)] == [
        [5, 4],
        [3, 2],
        [1],
    ]
    assert third.next_before_id is None


async def test_time_window_is_inclusive_since_exclusive_until(service):
    result = await service.get_messages(
        "10", since=NOW + timedelta(minutes=2), until=NOW + timedelta(minutes=4)
    )
    assert [m.message_id for m in result.messages] == [3, 2]
    assert result.next_before_id is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0},
        {"limit": 101},
        {"before_id": 0},
        {"since": NOW.replace(tzinfo=None)},
        {"since": NOW, "until": NOW},
    ],
)
async def test_bad_history_request_never_reaches_telegram(service, fake_client, kwargs):
    with pytest.raises(OperationError) as exc:
        await service.get_messages("10", **kwargs)
    assert exc.value.detail.code == "INVALID_REQUEST"
    fake_client.get_input_entity.assert_not_called()


@pytest.mark.parametrize("dialog_id", ["10", "-30", CHANNEL_ID])
async def test_send_uses_same_plain_text_contract(fake_client, dialog_id):
    service = TelegramService(fake_client, AccessPolicy(frozenset(), frozenset({dialog_id})))
    result = await service.send_message(dialog_id, "**literal text**", reply_to_message_id=1)
    fake_client.get_messages.assert_awaited_once_with(int(dialog_id), ids=1)
    fake_client.send_message.assert_awaited_once_with(
        int(dialog_id), "**literal text**", reply_to=1, parse_mode=None, link_preview=False
    )
    assert result.status == "sent"
    assert result.message.dialog_id == dialog_id


async def test_missing_reply_is_not_sent(service, fake_client):
    fake_client.get_messages.return_value = None
    with pytest.raises(OperationError) as exc:
        await service.send_message("10", "test", reply_to_message_id=1)
    assert exc.value.detail.delivery_status == "not_attempted"
    fake_client.send_message.assert_not_called()


@pytest.mark.parametrize("text", [" ", "a" * 4097, "😀" * 2049])
async def test_invalid_text_is_not_sent(service, fake_client, text):
    with pytest.raises(OperationError) as exc:
        await service.send_message("10", text)
    assert exc.value.detail.code == "INVALID_REQUEST"
    fake_client.send_message.assert_not_called()


async def test_rate_limit_returns_wait_without_retry(service, fake_client):
    fake_client.send_message.side_effect = errors.FloodWaitError(request=None, capture=17)
    with pytest.raises(OperationError) as exc:
        await service.send_message("10", "test")
    assert exc.value.detail.code == "RATE_LIMITED"
    assert exc.value.detail.retry_after_seconds == 17
    assert exc.value.detail.delivery_status == "rejected"
    fake_client.send_message.assert_awaited_once()


async def test_telegram_write_denial_is_rejected(service, fake_client):
    fake_client.send_message.side_effect = errors.ChatWriteForbiddenError(request=None)
    with pytest.raises(OperationError) as exc:
        await service.send_message(CHANNEL_ID, "test")
    assert exc.value.detail.code == "TELEGRAM_PERMISSION_DENIED"
    assert exc.value.detail.delivery_status == "rejected"
    fake_client.send_message.assert_awaited_once()


async def test_ambiguous_failure_does_not_leak_exception_or_retry(service, fake_client):
    fake_client.send_message.side_effect = OSError("SECRET_SENTINEL")
    with pytest.raises(OperationError) as exc:
        await service.send_message("10", "test")
    assert exc.value.detail.delivery_status == "unknown"
    assert "SECRET_SENTINEL" not in exc.value.detail.model_dump_json()
    fake_client.send_message.assert_awaited_once()


async def test_send_deadline_cancels_without_retry(service, fake_client, monkeypatch):
    monkeypatch.setattr("telegram_mcp.service.REQUEST_TIMEOUT_SECONDS", 0.01)

    async def delayed(*args, **kwargs):
        await asyncio.sleep(1)

    fake_client.send_message.side_effect = delayed
    with pytest.raises(OperationError) as exc:
        await service.send_message("10", "test")
    assert exc.value.detail.delivery_status == "unknown"
    fake_client.send_message.assert_awaited_once()


async def test_resolution_failure_is_not_attempted(service, fake_client):
    fake_client.get_input_entity.side_effect = ValueError("SECRET_SENTINEL")
    with pytest.raises(OperationError) as exc:
        await service.send_message("10", "test")
    assert exc.value.detail.code == "DIALOG_UNAVAILABLE"
    assert exc.value.detail.delivery_status == "not_attempted"
    fake_client.send_message.assert_not_called()


async def test_session_expiry_is_actionable(service, fake_client):
    fake_client.get_input_entity.side_effect = errors.AuthKeyUnregisteredError(request=None)
    with pytest.raises(OperationError) as exc:
        await service.get_messages("10")
    assert exc.value.detail.code == "SESSION_EXPIRED"
    assert "auth" in exc.value.detail.message


def test_channel_permissions_are_metadata_not_local_write_grants():
    ordinary = dialog_from_telegram(make_dialog(CHANNEL_ID, "channel"))
    admin = dialog_from_telegram(make_dialog(CHANNEL_ID, "channel", creator=True))
    assert ordinary.telegram_send_capability == "restricted"
    assert admin.telegram_send_capability == "allowed"
    assert not admin.write_allowed


def test_message_contract_keeps_sender_reply_and_media():
    message = make_message(1)
    message.reply_to = types.MessageReplyHeader(reply_to_msg_id=2)
    message.media = types.MessageMediaEmpty()
    result = message_from_telegram("10", message)
    assert result.sender_id == "20"
    assert result.reply_to_message_id == 2
    assert result.has_media
    assert result.date.tzinfo is not None
