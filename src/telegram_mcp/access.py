"""Server-enforced dialog allowlists, independent of agent instructions."""

from dataclasses import dataclass
from typing import Literal

from telegram_mcp.errors import OperationError
from telegram_mcp.models import Dialog, ErrorDetail


@dataclass(frozen=True)
class AccessPolicy:
    read_ids: frozenset[str]
    write_ids: frozenset[str]

    def visible(self, dialog_id: str) -> bool:
        return dialog_id in self.read_ids or dialog_id in self.write_ids

    def annotate(self, dialog: Dialog) -> Dialog:
        return dialog.model_copy(
            update={
                "read_allowed": dialog.dialog_id in self.read_ids,
                "write_allowed": dialog.dialog_id in self.write_ids,
            }
        )

    def require(self, dialog_id: str, action: Literal["read", "write"]) -> None:
        allowed = self.read_ids if action == "read" else self.write_ids
        if dialog_id not in allowed:
            raise OperationError(
                ErrorDetail(
                    code="ACCESS_DENIED",
                    message=f"This deployment does not permit {action} access to this dialog.",
                    delivery_status="not_attempted" if action == "write" else None,
                )
            )
