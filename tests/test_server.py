from contextlib import asynccontextmanager
from dataclasses import replace

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient

from telegram_mcp.server import create_app

HEADERS = {"Accept": "application/json, text/event-stream"}


@pytest.fixture
def http_client(settings, service):
    configured = replace(settings, mode="server", token="t" * 32)
    with TestClient(create_app(configured, service=service), base_url="http://localhost") as client:
        yield client


def call(client, method, params=None, headers=None):
    return client.post(
        "/mcp",
        headers={**HEADERS, "Authorization": "Bearer " + "t" * 32, **(headers or {})},
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )


@pytest.mark.parametrize("authorization", [None, "Bearer wrong", "Basic user:password"])
def test_all_mcp_calls_require_valid_token(http_client, authorization):
    headers = dict(HEADERS)
    if authorization is not None:
        headers["Authorization"] = authorization
    response = http_client.post("/mcp", headers=headers, json={})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "t" * 32 not in response.text


def test_health_has_no_account_data(http_client):
    assert http_client.get("/health").json() == {"status": "ok"}


def test_browser_origin_is_denied_even_with_valid_token(http_client):
    response = call(http_client, "tools/list", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_dns_rebinding_host_is_denied(http_client):
    response = call(http_client, "tools/list", headers={"Host": "evil.example"})
    assert response.status_code == 421


def test_tool_errors_have_mcp_error_flag_and_structured_details(http_client, fake_client):
    response = call(
        http_client,
        "tools/call",
        {"name": "send_message", "arguments": {"dialog_id": "99", "text": "test"}},
    )
    result = response.json()["result"]
    assert result["isError"]
    assert result["structuredContent"]["error"]["code"] == "ACCESS_DENIED"
    fake_client.send_message.assert_not_called()


def test_invalid_schema_input_never_reaches_telegram(http_client, fake_client):
    response = call(
        http_client,
        "tools/call",
        {"name": "get_messages", "arguments": {"dialog_id": "10", "limit": 101}},
    )
    assert response.json()["result"]["isError"]
    fake_client.get_input_entity.assert_not_called()


async def test_mcp_sdk_full_read_and_send_flow(settings, service, fake_client):
    configured = replace(settings, mode="server", token="t" * 32)
    app = create_app(configured, service=service)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost",
            headers={"Authorization": "Bearer " + "t" * 32},
        ) as http,
        streamable_http_client("http://localhost/mcp", http_client=http) as streams,
        ClientSession(streams[0], streams[1]) as session,
    ):
        await session.initialize()
        tools = (await session.list_tools()).tools
        assert {t.name for t in tools} == {"list_dialogs", "get_messages", "send_message"}
        send_tool = next(t for t in tools if t.name == "send_message")
        assert send_tool.annotations.idempotentHint is False
        dialogs = await session.call_tool("list_dialogs", {"limit": 2})
        assert not dialogs.isError
        assert len(dialogs.structuredContent["dialogs"]) == 2
        history = await session.call_tool("get_messages", {"dialog_id": "10"})
        assert history.structuredContent["messages"][0]["message_id"] == 5
        sent = await session.call_tool(
            "send_message", {"dialog_id": "10", "text": "test", "reply_to_message_id": 1}
        )
        assert not sent.isError
        assert sent.structuredContent["status"] == "sent"
    fake_client.send_message.assert_awaited_once()


def test_production_lifecycle_owns_account_and_uses_configured_policy(
    settings, fake_client, monkeypatch
):
    events = []

    @asynccontextmanager
    async def connection(config):
        events.append("connected")
        try:
            yield fake_client
        finally:
            events.append("disconnected")

    monkeypatch.setattr("telegram_mcp.server.connected_client", connection)
    configured = replace(settings, read_dialog_ids=frozenset({"10"}))
    with TestClient(create_app(configured), base_url="http://localhost") as client:
        result = call(client, "tools/call", {"name": "list_dialogs"}).json()["result"]
        assert [d["dialog_id"] for d in result["structuredContent"]["dialogs"]] == ["10"]
        assert events == ["connected"]
    assert events == ["connected", "disconnected"]
