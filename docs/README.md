# Baikal

Безопасный text-to-SQL сервис для университетской базы данных PostgreSQL.

Система принимает вопрос на естественном языке, превращает его в SQL-запрос,
исполняет строго через единственный шлюз доступа (пакет `db_mcp`) и возвращает
понятный ответ. В основе — жёсткий конвейер, который приоритизирует корректность
запроса, безопасность данных и стабильность системы.

## Монорепо-структура (uv workspace)

```
packages/db_mcp/   единственный шлюз к БД: безопасность, валидация, RLS, аудит
packages/app/      FastAPI-приложение: конвейер text-to-SQL поверх db_mcp
frontend/          React SPA: лендинг, чат, вход (по design.md)
db/                SQL: схема, роли, row-level security
scripts/seed.py    генератор синтетических данных
docs/              документация (индекс → docs/index.md)
```

## Быстрый старт

```bash
make sync                       # установить зависимости (uv sync --all-packages)
cp .env.example .env            # настроить подключение к БД (роли/пароли)
make db-up                      # поднять PostgreSQL в docker
make seed                       # заполнить базу синтетикой
make run                        # запустить приложение
```

## Полезные команды

```bash
make db-down    # остановить БД
make db-reset   # пересоздать БД с нуля (схема + роли + RLS)
make format     # форматирование (ruff)
make check      # lint + type check (ruff, ty)
make test       # pytest
```

## Веб-интерфейс (frontend)

SPA на React + Vite. Дизайн — в [design.md](design.md).

```bash
cd frontend
npm install      # установить зависимости (первый раз)
npm run dev      # dev-сервер на :5173, /api проксируется на :8000
npm run build    # production-сборка в frontend/dist
```

Пока бэкенд-эндпоинт `/api/v1/ask` не реализован, чат при недоступности
бэкенда отвечает локальным mock-ассистентом (детерминированно, по данным
сида). Вход по логину/паролю работает через реальный `/api/v1/auth/login`.

## Документация

Начни с [index.md](index.md) — там индекс всех документов и навигация
по темам.
