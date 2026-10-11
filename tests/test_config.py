from dataclasses import replace

import pytest

from telegram_mcp.config import ConfigurationError, Settings
from telegram_mcp.models import validate_dialog_id


@pytest.fixture
def configured_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "0" * 32)
    for name in (
        "TELEGRAM_SESSION_DIR",
        "TELEGRAM_READ_DIALOG_IDS",
        "TELEGRAM_WRITE_DIALOG_IDS",
        "MCP_MODE",
        "MCP_TOKEN",
        "MCP_HOST",
        "MCP_PORT",
        "MCP_ALLOWED_HOSTS",
        "MCP_ALLOWED_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_environment_defaults_deny_access(configured_env):
    settings = Settings.from_env()
    assert not settings.read_dialog_ids
    assert not settings.write_dialog_ids
    assert settings.mode == "local"
    assert settings.host == "127.0.0.1"
    settings.validate_http()


def test_environment_separates_read_and_write(configured_env):
    configured_env.setenv("TELEGRAM_READ_DIALOG_IDS", "10, -30")
    configured_env.setenv("TELEGRAM_WRITE_DIALOG_IDS", "10")
    settings = Settings.from_env()
    assert settings.read_dialog_ids == {"10", "-30"}
    assert settings.write_dialog_ids == {"10"}


@pytest.mark.parametrize(
    "name,value",
    [
        ("TELEGRAM_API_ID", "0"),
        ("TELEGRAM_API_ID", "SECRET_SENTINEL"),
        ("TELEGRAM_API_HASH", "SECRET_SENTINEL"),
        ("TELEGRAM_READ_DIALOG_IDS", "*"),
        ("TELEGRAM_WRITE_DIALOG_IDS", "10,"),
        ("MCP_MODE", "invalid"),
        ("MCP_PORT", "0"),
        ("MCP_PORT", "SECRET_SENTINEL"),
    ],
)
def test_invalid_environment_is_actionable_without_echoing_value(configured_env, name, value):
    configured_env.setenv(name, value)
    with pytest.raises(ConfigurationError) as exc:
        Settings.from_env()
    assert name in str(exc.value)
    assert "SECRET_SENTINEL" not in str(exc.value)


@pytest.mark.parametrize("value", ["0", "01", "+1", "1.0", " 1", str(2**63)])
def test_noncanonical_ids_are_rejected(value):
    with pytest.raises(ValueError):
        validate_dialog_id(value)


def test_configuration_repr_omits_credentials(settings):
    settings = replace(settings, api_hash="SECRET_HASH_SENTINEL", token="SECRET_TOKEN_SENTINEL")
    assert "SECRET" not in repr(settings)


def test_server_requires_token(settings):
    with pytest.raises(ConfigurationError, match="MCP_TOKEN"):
        replace(settings, mode="server").validate_http()
    with pytest.raises(ConfigurationError, match="32"):
        replace(settings, mode="server", token="short").validate_http()
    replace(settings, mode="server", token="t" * 32).validate_http()


def test_unrestricted_hosts_are_rejected(settings):
    with pytest.raises(ConfigurationError, match="explicit hosts"):
        replace(settings, allowed_hosts=("*",)).validate_http()
