# Auth-подсистема (JWT/пароль) — дизайн

Дата: 2026-08-24
Ветка: `dev`
Статус: утверждён (brainstorming)

## 1. Контекст и мотивация

Приложение `packages/app` (FastAPI, text-to-SQL поверх `db_mcp`) сейчас не имеет
аутентификации: роль и идентификатор пользователя передаются заголовками `X-Role` /
`X-User-Id` (прототип, см. ADR #4). Требуется полноценная аутентификация по
логину/паролю с выдачей JWT, трёхуровневой моделью доступа и админ-управлением
учётными записями.

Учётные записи живут в существующей университетской БД (таблица `users`, ADR #9),
а доступ к БД идёт **только через `db_mcp`** (ADR #3). Поэтому auth строится поверх
существующей таблицы `users` и шлюза, без отдельной БД и без прямого доступа из app.

## 2. Решения (изменения к ADR)

- **ADR #4 (заголовки X-Role/X-User-Id):** заменяется на JWT-аутентификацию по
  логину/паролю. Заголовки-хедеры как источник identity больше не используются;
  роль берётся из JWT.
- **ADR #9 (таблица users):** таблица расширяется полями для аутентификации
  (`email`, `password_hash`, `is_active`). Поле `external_id` сохраняется.
- **ADR #3 (единый шлюз):** сохраняется. Аутентификация идёт через новый метод
  `db_mcp`, app не обращается к БД напрямую.

## 3. Модель доступа

Три уровня:

1. **Аноним** — базовые запросы, только обезличенные/агрегированные данные
   (абитуриентский блок: направления, места, статистика прошлых лет).
2. **Авторизованный по роли** (applicant / student / teacher / admin) — расширенные
   возможности согласно `docs/about.md`. Роль берётся из JWT.
3. **Админ** — создание учётных записей, выдача ролей и прав.

Роли бизнес-уровня (applicant/student/teacher/admin) совпадают с `app/api/schemas.py`.

## 4. Схема БД (изменение таблицы `users`)

Текущая (`db/01_schema.sql`):

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR(100) NOT NULL UNIQUE,
    role VARCHAR(20) NOT NULL,
    internal_id INT,          -- student_id или staff_id
    display_name VARCHAR(150)
);
```

Изменения (миграция):

```sql
ALTER TABLE users ADD COLUMN email VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN password_hash VARCHAR(255);
ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;
```

- `email` — логин пользователя (UNIQUE). Допускает NULL на время перехода/для
  пользователей без логина; в нормальном потоке задаётся при создании учётки.
- `password_hash` — bcrypt-хэш пароля.
- `is_active` — флаг активности учётки (админ может блокировать).

Существующие поля сохраняются: `id`, `external_id`, `role`, `internal_id`,
`display_name`. `role` хранит роль бизнес-уровня; `internal_id` — ссылку на
`student_id`/`staff_id` для RLS-контекста.

## 5. db_mcp: метод шлюза для auth

db_mcp остаётся чистым шлюзом данных и НЕ аутентифицирует сам. Добавляется метод
шлюза, который по логину возвращает сохранённые данные учётки:

`get_user_credentials(login: str) -> UserCredentials | None`

Возвращает (по `email` или `external_id`):

```
{
  "id": int,
  "email": str | None,
  "external_id": str,
  "password_hash": str | None,
  "role": str,
  "internal_id": int | None,
  "display_name": str | None,
  "is_active": bool,
}
```

Доступ к `users` для auth выполняется служебной ролью БД (не `app_ro`):
`app_ro` лишена чтения `users` (см. `db/02_roles.sql`). Для auth-метода шлюза
используется отдельная роль/отдельное соединение с правом чтения нужных колонок
`users` (без PII-таблиц студентов и без `query_log`). Если логин не найден или
учётка неактивна — возвращается `None`/пустой результат.

## 6. app: auth-подсистема

### 6.1 Компоненты (`packages/app/src/app/`)

- `core/config.py` — `pydantic-settings` `Settings`: JWT секрет, алгоритм (HS256),
  срок жизни access-токена, параметры подключения к db_mcp.
- `core/security.py` — bcrypt (hash/verify), создание/декодирование JWT
  (claims: `sub` = internal_id, `role`, `email`, `exp`, `iat`).
- `services/auth.py` — сервис аутентификации:
  1. `get_user_credentials(login)` через db_mcp;
  2. проверка `is_active`;
  3. bcrypt-сравнение введённого пароля с `password_hash`;
  4. при успехе — выдача JWT (sub=internal_id, role).
- `auth/deps.py` — FastAPI-зависимости: `get_current_user` (Bearer → JWT →
  проверка/загрузка identity, иначе 401), `require_role(*roles)` (иначе 403).
- `auth/schemas.py` — pydantic-схемы: `LoginRequest`, `TokenResponse`,
  `UserCreate`, `UserUpdate`, `UserOut`.
- `auth/router.py` — `APIRouter` с эндпоинтами (см. ниже).

### 6.2 Эндпоинты

Открытые:
- `POST /api/v1/auth/login` — `{email, password}` → `{access_token,
  token_type: "bearer", role}`. 401 при неверных кредах/неактивной учётке.
- `POST /api/v1/auth/bootstrap-admin` — создание первого админа. Доступен, только
  если в `users` нет ни одной учётной записи с ролью `admin` (иначе 409).

Админ-эндпоинты (`require_role("admin")`), `/api/v1/auth/users`:
- `POST` — создать учётку `{email, password, role, external_id?}` → 201; 409 если
  email занят; 400 при невалидных данных (слабый пароль, неверная роль).
- `GET` — список учёток (без `password_hash`).
- `PATCH /{id}` — изменить `role`, `is_active`, сбросить пароль, `display_name`.
- `DELETE /{id}` — деактивировать учётку (мягкое удаление через `is_active=false`).

### 6.3 Обработка ошибок

- 401 — неверные креды, отсутствующий/невалидный/просроченный токен.
- 403 — токен валиден, но роль не позволяет операцию.
- 409 — email занят, bootstrap-admin при уже существующем админе.
- 400 — ошибки валидации (роль, пароль).
- Формат ошибок — стандартный FastAPI `{"detail": ...}`.

### 6.4 JWT ↔ RLS

Роль и `internal_id` из JWT в дальнейшем передаются в `db_mcp` при выполнении
запроса для установки RLS-контекста (`SET LOCAL app.role`, `app.user_id`).
Сопряжение с query-конвейером — вне рамок этой задачи (отдельный этап).

## 7. Миграции схемы

Схема БД управляется SQL-файлами в `db/` (инициализация контейнера). Изменение
таблицы `users` оформляется как новая миграция/ALTER в рамках текущего процесса
применения схемы (в соответствии с принятым в проекте способом — SQL-файлы, а не
Alembic, т.к. схема университетской БД идёт через `db/` + docker-init).

> Примечание: ранее в brainstorming рассматривался Alembic для отдельной auth БД;
> после решения «не отдельная БД» Alembic не требуется — миграция выполняется тем
> же механизмом, что и остальная схема (`db/01_schema.sql` и т.п.).

## 8. Тестирование

- pytest + httpx/TestClient (async).
- Юнит `core/security.py`: bcrypt hash/verify, JWT encode/decode (валидность,
  expiry).
- Юнит `services/auth.py`: выборка через db_mcp (мок), проверка is_active,
  bcrypt-сравнение, выдача JWT.
- Интеграционные: login успех/неудача (401), bootstrap-admin (только при пустом
  users, 409 иначе), админ-CRUD (201/409/400), enforce ролей (403), аноним без
  токена (401).

## 9. Границы (вне скоупа)

- Правила «какие запросы доступны какой роли» в query-конвейере и маскирование
  схемы — отдельный этап (services/query, db_mcp schema/validate).
- Сопряжение JWT с RLS при исполнении запросов — отдельный этап.
- SSO/внешний IdP — не сейчас.
- Обновление `docs/*` (architecture.md, decisions.md, roadmap.md) — выполняется
  вместе с этапом.
