# TelegramMCP

A self-hosted MCP service for reading and sending messages through your Telegram account. Private chats, groups, and channels share the same tools and dialog IDs. Telegram still enforces the account's permissions: subscribing to a channel does not grant permission to publish there.

## Deployment model

One Docker image exposes one Streamable HTTP MCP API at `/mcp`:

| Deployment | Connection |
| --- | --- |
| Local Docker service | An agent connects to `http://127.0.0.1:8000/mcp`. Compose publishes the port on loopback only. |
| Docker service on a server | A compatible remote client connects through an HTTPS reverse proxy with bearer authentication. |

Users operate their own deployments; no centrally hosted service is required. Each deployment uses one Telegram account and one persistent session. Run only one service or operator command against that session at a time.

Server mode currently supports a static bearer token. It does not yet implement OAuth or a published ChatGPT plugin. A browser or cloud integration that requires OAuth needs that additional implementation; deploying this version on a VPS alone does not make it compatible with every plugin host.

## Docker quick start

Install Docker with Compose. In WSL, enable Docker Desktop integration for your distribution.

1. Copy `.env.example` to `.env` and set `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` from [Telegram's application settings](https://my.telegram.org/apps).
2. Build the image and log in interactively:

   ```bash
   docker compose build
   docker compose run --rm telegram-mcp auth
   ```

   Enter your phone number, login code, and 2FA password if requested. The code and password use hidden terminal prompts. Login is an operator command and is never exposed to the agent.

3. Discover dialog IDs:

   ```bash
   docker compose run --rm telegram-mcp dialogs
   ```

   This owner-only command lists dialog IDs, names, and types. Add the IDs you choose to `TELEGRAM_READ_DIALOG_IDS` and/or `TELEGRAM_WRITE_DIALOG_IDS` in `.env`. Empty lists deny access; there is no wildcard. Reading and writing are independent permissions.

4. Start the service:

   ```bash
   docker compose up -d
   curl http://127.0.0.1:8000/health
   ```

   The health endpoint returns `{"status":"ok"}` after startup. It is a liveness endpoint, not a live check of Telegram connectivity.

Compose stores the session in the `telegram-session` named volume and runs the container as UID 10001 with a read-only root filesystem. Normal restarts and image rebuilds retain the session. `docker compose down -v` deletes the volume and requires a new login.

Stop the running service before another `auth` or `dialogs` command:

```bash
docker compose stop telegram-mcp
docker compose run --rm telegram-mcp dialogs
docker compose up -d
```

After changing `.env`, run `docker compose up -d` to recreate the service with the new configuration; a plain restart does not reload its environment.

## Connecting an agent

Choose Streamable HTTP and use `http://127.0.0.1:8000/mcp`. The service does not provide STDIO transport.

For a compatible client using MCP server configuration, set its server URL and, if configured, its bearer token. For example, Codex's `config.toml` can contain:

```toml
[mcp_servers.telegram]
url = "http://127.0.0.1:8000/mcp"
# Add this when MCP_TOKEN is configured; set the same token in the client environment.
# bearer_token_env_var = "TELEGRAM_MCP_CLIENT_TOKEN"
```

Agents inside another container cannot use the host's `127.0.0.1` address directly. Connect them through an explicitly configured private Docker network, require a token, and add the service hostname to `MCP_ALLOWED_HOSTS`.

## Server deployment

Use the same image and Compose file on your server:

- Set `MCP_MODE=server` and `MCP_TOKEN` to a random token of at least 32 characters.
- Add your public hostname to `MCP_ALLOWED_HOSTS`, retaining the local entries when needed. For example, append `mcp.example.com,mcp.example.com:*` after replacing the example domain.
- Keep the published Docker port on `127.0.0.1`; terminate HTTPS at a reverse proxy on the host.

[deploy/Caddyfile](deploy/Caddyfile) provides a starting configuration for Caddy running on the host. Replace its hostname, point DNS at the server, and configure Caddy separately. Clients use `https://YOUR_HOST/mcp` and the header `Authorization: Bearer YOUR_TOKEN`. The proxy must preserve this header. The application does not trust forwarded headers or provide TLS itself.

Browser Origin headers are denied by default. This service is designed for MCP hosts making server-to-server requests; it does not enable CORS for direct browser JavaScript. An Origin allowlist does not add OAuth or CORS support.

## Tools

All tools return JSON in both MCP text content and structured content. Dialog IDs are canonical signed decimal strings so JavaScript clients do not lose integer precision. Obtain them from `list_dialogs` or the operator command; names and usernames are not accepted as IDs.

| Tool | Parameters | Result |
| --- | --- | --- |
| `list_dialogs` | `limit` (1–100, default 50), optional `cursor` | Allowed dialogs with type, local read/write permissions, Telegram send capability hint, and `next_cursor`. |
| `get_messages` | `dialog_id`, `limit`, optional `before_id`, `since`, `until` | Messages newest first and `next_before_id`. |
| `send_message` | `dialog_id`, `text`, optional `reply_to_message_id` | `status: "sent"` and the sent message. |

Dialog pages sort by numeric ID; pass `next_cursor` to the next call. Listing enumerates the account's dialogs before filtering and pagination, so large accounts may take longer. Changes in membership between calls can change the available results.

For history, pass `next_before_id` as `before_id`. `before_id` is exclusive, `since` is inclusive, and `until` is exclusive. Time filters must include a timezone, such as `2026-01-01T09:00:00+03:00`. Each message includes its ID, timestamp, available sender ID, text, reply target, and whether it has media; media files are not downloaded.

Sending accepts nonblank plain text up to 4096 UTF-16 code units. Markdown formatting and link previews are disabled. A reply target must exist in the same dialog. Local write permission does not override Telegram restrictions; capability metadata is only a hint, and Telegram makes the final decision.

Telegram operation and access failures set MCP `isError: true` and return an `error` object with `code`, `message`, optional `retry_after_seconds`, and optional `delivery_status`. Invalid tool arguments can also produce SDK validation errors with `isError: true`.

Delivery status values are:

- `not_attempted`: sending was blocked or failed before the send call.
- `rejected`: Telegram explicitly rejected the send, including rate limits.
- `unknown`: the send may have succeeded, but confirmation was lost. Inspect the chat in Telegram before deciding whether to resend.

The service disables Telethon's automatic request retries and automatic flood-wait sleeps. Telegram operations have a 30-second deadline; send preflight and sending each have their own deadline. It never automatically repeats a failed send. It does not deduplicate separate tool calls made by a client, so clients must not blindly retry `send_message`.

## Configuration and account data

| Environment variable | Purpose / default |
| --- | --- |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | Required Telegram application credentials. |
| `TELEGRAM_SESSION_DIR` | Session storage; `./data` natively, `/data` in Compose. |
| `TELEGRAM_READ_DIALOG_IDS` | Comma-separated IDs allowed for history; empty denies all. |
| `TELEGRAM_WRITE_DIALOG_IDS` | Comma-separated IDs allowed for sending; empty denies all. |
| `MCP_MODE` | `local` (default) or `server`. |
| `MCP_TOKEN` | Optional locally, required in server mode; at least 32 characters. |
| `MCP_HOST`, `MCP_PORT` | Native bind address `127.0.0.1:8000`; Compose binds inside the container to `0.0.0.0:8000`. |
| `MCP_ALLOWED_HOSTS` | Explicit Host allowlist; defaults to localhost and loopback with and without ports. Bare `*` is rejected. |
| `MCP_ALLOWED_ORIGINS` | Exact comma-separated origins; empty denies requests with an Origin header. |

Telegram credentials come from the environment. Account sessions stay in the user's volume; credential values and raw Telegram exceptions are not included in tool results. Applications with access to the environment or volume can still read those secrets. Keep `.env` and session files out of version control and backups intended for sharing. Requested messages are returned to the model for processing.

## Development and verification

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv sync --locked --python 3.12
uv run --env-file .env telegram-mcp auth
uv run --env-file .env telegram-mcp dialogs
uv run --env-file .env telegram-mcp serve
```

Run operator commands before starting `serve`. Native session locking requires a Unix-like environment; Docker is the supported route on Windows. The application uses the MCP SDK 1.x API with dependencies pinned in `uv.lock`.

```bash
uv run pytest -q
uv run ruff check --select E,W,F,B,I,UP,SIM,FURB,PLW1510,RUF100 --line-length 100 src tests
uv run ruff format --line-length 100 --check src tests
uv run mypy --check-untyped-defs --ignore-missing-imports --warn-redundant-casts --warn-unused-ignores src
git diff --check
```

Tests use a fake Telegram client, including a complete exchange through the real MCP client/server SDK. They never log in to Telegram or send real messages. CI also builds the Docker image. A real-account acceptance check must be performed separately with an explicitly chosen test dialog: list it, read its history, send a message, restart the service, and verify the saved session still works.

Scheduled digests, search, OAuth, file transfer, message editing, and reactions are outside this first version. Scheduling belongs to a connected client or a separate scheduler; this service must be running and reachable whenever a task executes.
