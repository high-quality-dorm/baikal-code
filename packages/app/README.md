# app

FastAPI-приложение Baikal: тонкий HTTP-слой поверх пакета `db`.

Три эндпоинта:

- `POST /api/v1/auth/login` — вход по email/паролю → JWT (`sub` = номер учётки).
- `GET /api/v1/auth/users/me` — текущая учётка с производной ролью (для бейджа).
- `POST /api/v1/ask` — конвейер text-to-SQL; гость разрешён (без токена).

Роль не хранится в токене — резолвится на каждый запрос через `db.resolve_role`.
Учётные записи и связки `student_id`/`staff_id` заводятся вне приложения.

## Запуск

```bash
make sync     # установить зависимости
make certs    # сгенерировать ключи JWT (RS256)
make run      # uvicorn на 127.0.0.1:8000
```

Значения LLM (`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`) и строки подключения к БД
(`DATABASE_URL_RO`/`DATABASE_URL_SERVICE`) заполняются в `.env`.

## Тесты

`make test` (все тесты репозитория, включая `tests/` для app) и `make check`
(ty + ruff + проверка документации).

Детали архитектуры — в `docs/architecture.md` (пакет `packages/app`) и
`docs/decisions.md` (ADR 34–35).