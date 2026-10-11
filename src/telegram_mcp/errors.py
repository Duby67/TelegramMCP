"""Translate failures without returning raw Telegram responses or exception messages."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from telethon import errors

from telegram_mcp.models import ErrorDetail


class OperationError(RuntimeError):
    def __init__(self, detail: ErrorDetail) -> None:
        self.detail = detail
        super().__init__(detail.message)


def invalid_request(message: str, *, sending: bool = False) -> OperationError:
    return OperationError(
        ErrorDetail(
            code="INVALID_REQUEST",
            message=message,
            delivery_status="not_attempted" if sending else None,
        )
    )


@contextmanager
def telegram_errors(*, sending: bool = False, attempted: bool = False) -> Iterator[None]:
    try:
        yield
    except OperationError:
        raise
    except Exception as exc:
        status: Literal["not_attempted", "rejected", "unknown"] | None = (
            "not_attempted" if sending else None
        )
        if sending and attempted:
            status = "unknown"
        code = "TELEGRAM_UNAVAILABLE"
        message = "Telegram operation failed. Check service connectivity and account status."
        retry_after = None
        if isinstance(exc, (errors.FloodWaitError, errors.SlowModeWaitError)):
            code = "RATE_LIMITED"
            message = "Telegram rate limit reached. Wait before making another request."
            retry_after = exc.seconds
            if sending and attempted:
                status = "rejected"
        elif isinstance(exc, (errors.AuthKeyUnregisteredError, errors.SessionRevokedError)):
            code = "SESSION_EXPIRED"
            message = "Stop the service and run 'telegram-mcp auth' to authorize again."
            if sending and attempted:
                status = "rejected"
        elif isinstance(exc, (errors.ChannelPrivateError, errors.PeerIdInvalidError)):
            code = "DIALOG_UNAVAILABLE"
            message = "Dialog is unavailable to this Telegram account."
            if sending and attempted:
                status = "rejected"
        elif isinstance(exc, (errors.ForbiddenError, errors.UnauthorizedError)):
            code = "TELEGRAM_PERMISSION_DENIED"
            message = "Telegram denied the operation. Check the account's dialog permissions."
            if sending and attempted:
                status = "rejected"
        elif isinstance(exc, errors.BadRequestError):
            code = "TELEGRAM_REJECTED"
            message = "Telegram rejected the request. Check the dialog and message parameters."
            if sending and attempted:
                status = "rejected"
        elif isinstance(exc, ValueError) and not attempted:
            code = "DIALOG_UNAVAILABLE"
            message = "Cannot resolve this dialog. Call list_dialogs and use an ID it returns."
        if status == "unknown":
            message = (
                "Delivery status is unknown. Do not repeat the send automatically; "
                "inspect the chat in Telegram before deciding whether to resend."
            )
        raise OperationError(
            ErrorDetail(
                code=code,
                message=message,
                retry_after_seconds=retry_after,
                delivery_status=status,
            )
        ) from None
