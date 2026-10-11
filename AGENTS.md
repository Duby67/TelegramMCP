TelegramMCP is a self-hosted MCP service for access to a user's Telegram account. The intended deployment contract is owned by [README.md](README.md).

## Rules

- Commit, push, PR, and merge belong to the user.
- No silent fallback: fail with an actionable error.
- Secrets come from the environment; never commit or log them.
- Never report an unrun or skipped check as passed; run checks after the last change.
- Start another agent only with the user's permission.
- When docs, config, code, and tests disagree, report the contradiction instead of choosing.
- Do not create plan, summary, or notes files unless asked.

## Language

- Agent-facing files and human documentation are in English; change the documentation language only when the user asks.
