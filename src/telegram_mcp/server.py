"""Authenticated Streamable HTTP service with explicit startup and shutdown."""

import hmac
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from telegram_mcp.access import AccessPolicy
from telegram_mcp.account import connected_client
from telegram_mcp.config import Settings
from telegram_mcp.service import TelegramService
from telegram_mcp.tools import create_mcp


class AccessMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] != "/health":
            request = Request(scope)
            if self.settings.token is not None:
                supplied = request.headers.get("authorization", "")
                expected = "Bearer " + self.settings.token
                if not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
                    response = JSONResponse(
                        {"error": "Authentication required."},
                        status_code=401,
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                    await response(scope, receive, send)
                    return
            origin = request.headers.get("origin")
            if origin is not None and origin not in self.settings.allowed_origins:
                await JSONResponse({"error": "Origin is not allowed."}, status_code=403)(
                    scope, receive, send
                )
                return
        await self.app(scope, receive, send)


class MCPDispatch:
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await scope["app"].state.mcp_app(scope, receive, send)


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_app(settings: Settings, *, service: TelegramService | None = None) -> Starlette:
    settings.validate_http()

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            active_service = service
            if active_service is None:
                client = await stack.enter_async_context(connected_client(settings))
                active_service = TelegramService(
                    client, AccessPolicy(settings.read_dialog_ids, settings.write_dialog_ids)
                )
            security = TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=list(settings.allowed_hosts),
                allowed_origins=list(settings.allowed_origins),
            )
            mcp = create_mcp(active_service, security)
            app.state.mcp_app = mcp.streamable_http_app()
            await stack.enter_async_context(mcp.session_manager.run())
            yield

    return Starlette(
        routes=[Route("/health", health), Route("/mcp", MCPDispatch())],
        middleware=[Middleware(AccessMiddleware, settings=settings)],
        lifespan=lifespan,
    )


def serve(settings: Settings) -> None:
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        access_log=False,
        log_level="warning",
        proxy_headers=False,
    )
