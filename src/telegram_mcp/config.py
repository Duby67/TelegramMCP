"""Environment configuration without secret-bearing representations."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from telegram_mcp.models import validate_dialog_id


class ConfigurationError(ValueError):
    """An invalid deployment setting, safe to display to the operator."""


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str = field(repr=False)
    session_dir: Path
    read_dialog_ids: frozenset[str] = field(default_factory=frozenset)
    write_dialog_ids: frozenset[str] = field(default_factory=frozenset)
    mode: Literal["local", "server"] = "local"
    token: str | None = field(default=None, repr=False)
    host: str = "127.0.0.1"
    port: int = 8000
    allowed_hosts: tuple[str, ...] = (
        "localhost",
        "localhost:*",
        "127.0.0.1",
        "127.0.0.1:*",
        "[::1]",
        "[::1]:*",
    )
    allowed_origins: tuple[str, ...] = ()

    @property
    def session_path(self) -> Path:
        return self.session_dir / "telegram.session"

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            api_id = int(os.environ.get("TELEGRAM_API_ID", ""))
        except ValueError:
            raise ConfigurationError("Set TELEGRAM_API_ID to a positive integer.") from None
        if api_id <= 0:
            raise ConfigurationError("Set TELEGRAM_API_ID to a positive integer.")
        api_hash = os.environ.get("TELEGRAM_API_HASH", "")
        if len(api_hash) != 32 or any(c not in "0123456789abcdef" for c in api_hash.lower()):
            raise ConfigurationError("Set TELEGRAM_API_HASH to the 32-character API hash.")
        session_dir = Path(os.environ.get("TELEGRAM_SESSION_DIR", "./data"))
        mode = os.environ.get("MCP_MODE", "local")
        if mode not in ("local", "server"):
            raise ConfigurationError("MCP_MODE must be local or server.")
        try:
            port = int(os.environ.get("MCP_PORT", "8000"))
        except ValueError:
            raise ConfigurationError("MCP_PORT must be an integer between 1 and 65535.") from None
        if not 1 <= port <= 65535:
            raise ConfigurationError("MCP_PORT must be between 1 and 65535.")
        return cls(
            api_id=api_id,
            api_hash=api_hash,
            session_dir=session_dir,
            read_dialog_ids=dialog_ids_from_env("TELEGRAM_READ_DIALOG_IDS"),
            write_dialog_ids=dialog_ids_from_env("TELEGRAM_WRITE_DIALOG_IDS"),
            mode="server" if mode == "server" else "local",
            token=os.environ.get("MCP_TOKEN") or None,
            host=os.environ.get("MCP_HOST", "127.0.0.1"),
            port=port,
            allowed_hosts=tuple(
                part.strip()
                for part in os.environ.get(
                    "MCP_ALLOWED_HOSTS", "localhost,localhost:*,127.0.0.1,127.0.0.1:*,[::1],[::1]:*"
                ).split(",")
                if part.strip()
            ),
            allowed_origins=tuple(
                part.strip()
                for part in os.environ.get("MCP_ALLOWED_ORIGINS", "").split(",")
                if part.strip()
            ),
        )

    def validate_http(self) -> None:
        if self.mode == "server" and self.token is None:
            raise ConfigurationError("Server mode requires MCP_TOKEN (at least 32 characters).")
        if self.token is not None and len(self.token) < 32:
            raise ConfigurationError("MCP_TOKEN must contain at least 32 characters.")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            raise ConfigurationError("MCP_ALLOWED_HOSTS must name explicit hosts, not '*'.")


def dialog_ids_from_env(name: str) -> frozenset[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return frozenset()
    ids = frozenset(part.strip() for part in raw.split(","))
    try:
        for dialog_id in ids:
            validate_dialog_id(dialog_id)
    except ValueError:
        raise ConfigurationError(
            f"Set {name} to comma-separated dialog IDs from 'telegram-mcp dialogs'."
        ) from None
    return ids
