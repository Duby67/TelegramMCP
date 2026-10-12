"""Persistent, default-deny dialog permissions confirmed through a trusted MCP host."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from telegram_mcp.errors import OperationError
from telegram_mcp.models import Dialog, ErrorDetail, validate_dialog_id

Access = Literal["read", "write"]


class AccessPolicy:
    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        os.umask(0o077)
        try:
            storage_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self.database() as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS permissions ("
                    "dialog_id TEXT NOT NULL, "
                    "action TEXT NOT NULL CHECK(action IN ('read', 'write')), "
                    "PRIMARY KEY(dialog_id, action))"
                )
            storage_path.chmod(0o600)
        except OSError:
            raise self.storage_error() from None

    @staticmethod
    def storage_error() -> OperationError:
        return OperationError(
            ErrorDetail(
                code="ACCESS_STORAGE_UNAVAILABLE",
                message="Cannot access permission storage. Check volume permissions and integrity.",
            )
        )

    @contextmanager
    def database(self) -> Iterator[sqlite3.Connection]:
        try:
            db = sqlite3.connect(self.storage_path, timeout=5)
            try:
                with db:
                    yield db
            finally:
                db.close()
        except sqlite3.Error:
            raise self.storage_error() from None

    def allowed(self, dialog_id: str, action: Access) -> bool:
        with self.database() as db:
            return (
                db.execute(
                    "SELECT 1 FROM permissions WHERE dialog_id = ? AND action = ?",
                    (dialog_id, action),
                ).fetchone()
                is not None
            )

    def grant(self, dialog_id: str, action: Access) -> None:
        """Internal operation: call only after a trusted user confirmation."""
        validate_dialog_id(dialog_id)
        with self.database() as db:
            db.execute(
                "INSERT OR IGNORE INTO permissions(dialog_id, action) VALUES (?, ?)",
                (dialog_id, action),
            )

    def revoke(self, dialog_id: str, action: Access) -> None:
        validate_dialog_id(dialog_id)
        with self.database() as db:
            db.execute(
                "DELETE FROM permissions WHERE dialog_id = ? AND action = ?", (dialog_id, action)
            )

    def annotate(self, dialog: Dialog) -> Dialog:
        return dialog.model_copy(
            update={
                "read_allowed": self.allowed(dialog.dialog_id, "read"),
                "write_allowed": self.allowed(dialog.dialog_id, "write"),
            }
        )

    def require(self, dialog_id: str, action: Access) -> None:
        if not self.allowed(dialog_id, action):
            raise OperationError(
                ErrorDetail(
                    code="ACCESS_DENIED",
                    message=(
                        f"User confirmation is required for {action} access to this dialog. "
                        "Call request_dialog_access to ask the user."
                    ),
                    delivery_status="not_attempted" if action == "write" else None,
                )
            )
