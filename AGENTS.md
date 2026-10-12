TelegramMCP is a self-hosted MCP service for access to a user's Telegram account. The intended deployment contract is owned by [README.md](README.md).

## Rules

- Commit, push, PR, and merge belong to the user.
- No silent fallback: fail with an actionable error.
- Secrets come from the environment; never commit or log them.
- Never report an unrun or skipped check as passed; run checks after the last change.
- Start another agent only with the user's permission.
- When docs, config, code, and tests disagree, report the contradiction instead of choosing.

## Work

- Make the smallest correct change. Prefer, in order: no change, existing code, the standard library, an installed dependency, new code. Stay in scope.
- Read narrowly: focused search, bounded reads, `git diff --stat` before diffs, quiet test output.
- Never read or search `uv.lock`, `dist/`, `data/`, `.venv/`, `.mypy_cache/`, `.pytest_cache/`, or `.ruff_cache/`.
- Fastest checks: `uv run pytest -q tests/<file>.py::<test>`, `uv run ruff check --select E,W,F,B,I,UP,SIM,FURB,PLW1510,RUF100 --line-length 100 <files>`, `uv run mypy --check-untyped-defs --ignore-missing-imports --warn-redundant-casts --warn-unused-ignores src`; the full set is in `.github/workflows/check.yml`.
- Do not create plan, summary, or notes files unless asked.
- Keep the repository root minimal: put a new file in an existing directory or its tool's own (`docs/`, `.claude/`, `.github/`); add a root file only where a tool requires it.

## Language

- Agent-facing files (`AGENTS.md`, `.claude/CLAUDE.md`) are in English. Human docs are in English, translated to: ru; add or remove a language only when the user asks.

## Report

One line per point: result, checks run with outcome, concrete risks. Write nothing else: no empty categories, no actions not taken (such as "not committed"), nothing the user already sees.
