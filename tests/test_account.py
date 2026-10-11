import stat
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telethon.errors import SessionPasswordNeededError

from telegram_mcp import account
from telegram_mcp.account import AccountError, authorize, connected_client, create_client


@pytest.fixture
def account_client(settings, monkeypatch):
    client = SimpleNamespace(
        connect=AsyncMock(),
        disconnect=AsyncMock(),
        is_user_authorized=AsyncMock(return_value=True),
        send_code_request=AsyncMock(return_value=SimpleNamespace(phone_code_hash="test-code-hash")),
        sign_in=AsyncMock(),
    )

    def factory(config):
        config.session_path.touch()
        return client

    monkeypatch.setattr(account, "create_client", factory)
    return client


async def test_missing_session_fails_before_connect(settings, account_client):
    with pytest.raises(AccountError, match="auth"):
        async with connected_client(settings):
            pytest.fail("Missing session should prevent startup")
    account_client.connect.assert_not_called()


async def test_session_is_exclusive_and_private(settings, account_client):
    async with connected_client(settings, require_authorized=False):
        assert stat.S_IMODE(settings.session_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(settings.session_path.stat().st_mode) == 0o600
        with pytest.raises(AccountError, match="already in use"):
            async with connected_client(settings):
                pytest.fail("Concurrent session access should fail")
    account_client.disconnect.assert_awaited_once()
    async with connected_client(settings):
        pass
    assert account_client.connect.await_count == 2


async def test_expired_session_disconnects(settings, account_client):
    settings.session_dir.mkdir()
    settings.session_path.touch()
    account_client.is_user_authorized.return_value = False
    with pytest.raises(AccountError, match="expired"):
        async with connected_client(settings):
            pytest.fail("Expired session should prevent startup")
    account_client.disconnect.assert_awaited_once()


async def test_login_handles_2fa_without_printing_credentials(
    settings, account_client, monkeypatch, capsys
):
    account_client.is_user_authorized.return_value = False
    account_client.sign_in.side_effect = [SessionPasswordNeededError(request=None), None]
    monkeypatch.setattr("builtins.input", lambda prompt: "test-phone")
    answers = iter(["test-login-code", "SECRET_SENTINEL"])
    monkeypatch.setattr(account, "getpass", lambda prompt: next(answers))
    await authorize(settings)
    assert account_client.sign_in.await_count == 2
    account_client.sign_in.assert_awaited_with(password="SECRET_SENTINEL")
    captured = capsys.readouterr()
    assert "SECRET_SENTINEL" not in captured.out + captured.err
    assert "saved" in captured.out


async def test_login_failure_does_not_expose_telegram_exception(
    settings, account_client, monkeypatch, capsys
):
    account_client.is_user_authorized.return_value = False
    account_client.send_code_request.side_effect = RuntimeError("SECRET_SENTINEL")
    monkeypatch.setattr("builtins.input", lambda prompt: "test-phone")
    with pytest.raises(AccountError) as exc:
        await authorize(settings)
    assert "SECRET_SENTINEL" not in str(exc.value)
    assert "SECRET_SENTINEL" not in capsys.readouterr().out
    account_client.disconnect.assert_awaited_once()


async def test_telethon_automatic_request_retries_are_disabled(settings):
    settings.session_dir.mkdir()
    client = create_client(settings)
    try:
        assert client._request_retries == 0
        assert client.flood_sleep_threshold == 0
    finally:
        await client.disconnect()


async def test_session_open_failure_is_safe_and_releases_lock(settings, monkeypatch):
    def broken_factory(config):
        raise RuntimeError("SECRET_SENTINEL")

    monkeypatch.setattr(account, "create_client", broken_factory)
    for _ in range(2):
        with pytest.raises(AccountError, match="Cannot open") as exc:
            async with connected_client(settings, require_authorized=False):
                pytest.fail("Broken session should prevent startup")
        assert "SECRET_SENTINEL" not in str(exc.value)
