
# AGENTS.md

## Project Overview

This project is an AI-powered assistant designed to provide secure, scalable, and controlled natural language access to the university's PostgreSQL database. Functioning as a secure text-to-SQL connector, it implements a strict execution pipeline—from user query to validated database response—that heavily prioritizes query correctness, data security, and overall system stability.

## Architecture

- Think through the architecture upfront — no quick MVP "to test it first".
- Build it properly from the start.

## Commands

```bash
make run      # run the app
make format   # format code (ruff)
make check    # lint + type check (ruff, ty)
uv sync       # install dependencies
```

## Code Style

- Python 3.13 features: type hints, `str | None`, `list[T]`
- Comments in code are welcome and encouraged for non-obvious decisions
- Formatting and linting are done via `make format` / `make check` — use them, not the tools directly
- Conventional commits: `init:`, `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:` (+ optional scope, e.g. `docs(ai):`)
- Follow existing patterns in the project
- If unsure about style or approach — ask the user

## Working with the AI

- Never guess. In unclear situations don't try to figure things out on your own — stop and ask the user.
- If something unexpected happens (errors, unusual behavior, unexpected results) — stop and ask the user.
- Before important decisions (project structure, architecture, changing logic) — propose options and ask.
- Clarify ambiguous requirements instead of deciding for the user.
- Run `make format` and `make check` before committing.
- When making changes, explain what changes and how the changed code works.
- Minimal output — maximum usefulness.
