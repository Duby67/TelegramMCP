"""Environment configuration without secret-bearing representations."""

import os
from dataclasses import dataclass, field
from pathlib import Path


class ConfigurationError(ValueError):
    """An invalid deployment setting, safe to display to the operator."""


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str = field(repr=False)
    session_dir: Path

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
        return cls(api_id=api_id, api_hash=api_hash, session_dir=session_dir)
