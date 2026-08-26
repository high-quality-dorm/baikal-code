# Образ бэкенда Baikal для продакшена.
#
# Секреты (пароли БД, LLM-ключ) и JWT-ключи не зашиваются в образ:
#   - секреты передаются через переменные окружения (env_file в compose);
#   - JWT-ключи монтируются volume'ом (certs/).
#
# В контексте сборки лежит корень репозитория (docker build -f deploy/Dockerfile .).

FROM python:3.12-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# uv — менеджер пакетов и окружений проекта.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Сначала зависимости — чтобы кэшировать слой сборки (uv.lock стабилен).
COPY pyproject.toml uv.lock ./
COPY packages/db/pyproject.toml packages/db/pyproject.toml
COPY packages/app/pyproject.toml packages/app/pyproject.toml
COPY packages/db packages/db
COPY packages/app packages/app

# Собираем только пакет app (тянет db из workspace), без dev-зависимостей.
RUN uv sync --no-dev --package app

ENV PATH="/app/.venv/bin:$PATH"

# JWT-ключи по умолчанию ищутся в certs/ (volume монтируется поверх в compose).
EXPOSE 8000

# Один worker: rate limiting in-process (ADR 37) — при нескольких процессах
# лимит считался бы per-process. Работаем на 0.0.0.0 внутри docker-сети.
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
