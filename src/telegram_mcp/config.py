"""Environment configuration without secret-bearing representations."""

import os
from dataclasses import dataclass, field
from pathlib import Path

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
        return cls(
            api_id=api_id,
            api_hash=api_hash,
            session_dir=session_dir,
            read_dialog_ids=dialog_ids_from_env("TELEGRAM_READ_DIALOG_IDS"),
            write_dialog_ids=dialog_ids_from_env("TELEGRAM_WRITE_DIALOG_IDS"),
        )


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
