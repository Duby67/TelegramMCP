import asyncio
import socket
import threading
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import uvicorn
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from mcp.server.elicitation import AcceptedElicitation, CancelledElicitation, DeclinedElicitation

from telegram_mcp.access import AccessPolicy
from telegram_mcp.errors import OperationError
from telegram_mcp.server import create_app
from telegram_mcp.tools import AccessConfirmation, request_access, revoke_access


def confirmation_context(confirmation=None, supported=True):
    return SimpleNamespace(
        session=SimpleNamespace(check_client_capability=lambda capability: supported),
        elicit=AsyncMock(return_value=confirmation),
    )


@pytest.mark.parametrize("access", ["read", "write"])
async def test_confirmed_permission_persists_and_is_scoped(service, tmp_path, access):
    ctx = confirmation_context(AcceptedElicitation(data=AccessConfirmation(approve=True)))
    result = await request_access(service, ctx, "99", access)
    assert result.status == "granted"
    other = "write" if access == "read" else "read"
    assert not service.policy.allowed("99", other)
    assert not service.policy.allowed("98", access)
    assert AccessPolicy(tmp_path / "permissions.sqlite").allowed("99", access)
    prompt = ctx.elicit.call_args.kwargs["message"]
    assert "ID 99" in prompt
    assert "test-private" in prompt
    assert "persists" in prompt


@pytest.mark.parametrize(
    "confirmation,status",
    [
        (AcceptedElicitation(data=AccessConfirmation(approve=False)), "denied"),
        (DeclinedElicitation(), "denied"),
        (CancelledElicitation(), "cancelled"),
    ],
)
async def test_decline_false_and_cancel_do_not_grant(service, confirmation, status):
    result = await request_access(service, confirmation_context(confirmation), "99", "read")
    assert result.status == status
    assert not service.policy.allowed("99", "read")


async def test_unsupported_client_cannot_grant(service):
    ctx = confirmation_context(supported=False)
    with pytest.raises(OperationError) as exc:
        await request_access(service, ctx, "99", "read")
    assert exc.value.detail.code == "CONFIRMATION_UNAVAILABLE"
    assert not service.policy.allowed("99", "read")
    ctx.elicit.assert_not_called()


async def test_confirmation_failure_leaves_permissions_unchanged(service):
    ctx = confirmation_context()
    ctx.elicit.side_effect = RuntimeError("SECRET_SENTINEL")
    with pytest.raises(OperationError) as exc:
        await request_access(service, ctx, "99", "write")
    assert exc.value.detail.code == "CONFIRMATION_UNAVAILABLE"
    assert "SECRET_SENTINEL" not in str(exc.value)
    assert not service.policy.allowed("99", "write")


async def test_already_granted_does_not_prompt_again(service):
    ctx = confirmation_context()
    result = await request_access(service, ctx, "10", "read")
    assert result.status == "already_granted"
    ctx.elicit.assert_not_called()


async def test_unknown_dialog_does_not_prompt(service):
    ctx = confirmation_context()
    with pytest.raises(OperationError):
        await request_access(service, ctx, "123", "write")
    ctx.elicit.assert_not_called()


async def test_revoke_is_persistent_and_preserves_other_permission(service, tmp_path):
    await revoke_access(service, "10", "read")
    restored = AccessPolicy(tmp_path / "permissions.sqlite")
    assert not restored.allowed("10", "read")
    assert restored.allowed("10", "write")
    with pytest.raises(OperationError):
        await service.get_messages("10")


def test_corrupt_storage_fails_closed(tmp_path):
    path = tmp_path / "permissions.sqlite"
    path.write_text("not a sqlite database")
    with pytest.raises(OperationError) as exc:
        AccessPolicy(path)
    assert exc.value.detail.code == "ACCESS_STORAGE_UNAVAILABLE"


@pytest.fixture
def live_url(settings, service):
    app = create_app(replace(settings, token="t" * 32), service=service)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="critical", access_log=False, timeout_graceful_shutdown=1)
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    try:
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "Test HTTP server did not start"
        yield f"http://127.0.0.1:{listener.getsockname()[1]}/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        assert not thread.is_alive(), "Test HTTP server did not shut down"


async def test_real_http_sdk_confirmation_grants_only_accepted_scope(live_url, service):
    import httpx

    choices = iter([True, False])

    async def user_confirmation(context, params):
        assert "ID 99" in params.message
        assert params.requestedSchema["properties"]["approve"]["default"] is False
        return types.ElicitResult(action="accept", content={"approve": next(choices)})

    async with (
        asyncio.timeout(10),
        httpx.AsyncClient(headers={"Authorization": "Bearer " + "t" * 32}) as http,
        streamable_http_client(live_url, http_client=http) as streams,
        ClientSession(streams[0], streams[1], elicitation_callback=user_confirmation) as session,
    ):
        await session.initialize()
        denied = await session.call_tool("get_messages", {"dialog_id": "99"})
        assert denied.isError
        accepted = await session.call_tool(
            "request_dialog_access", {"dialog_id": "99", "access": "read"}
        )
        assert not accepted.isError
        assert accepted.structuredContent["status"] == "granted"
        read = await session.call_tool("get_messages", {"dialog_id": "99"})
        assert not read.isError
        rejected = await session.call_tool(
            "request_dialog_access", {"dialog_id": "99", "access": "write"}
        )
        assert rejected.structuredContent["status"] == "denied"
        assert not service.policy.allowed("99", "write")
        revoked = await session.call_tool(
            "revoke_dialog_access", {"dialog_id": "99", "access": "read"}
        )
        assert revoked.structuredContent["status"] == "revoked"
        assert not service.policy.allowed("99", "read")
