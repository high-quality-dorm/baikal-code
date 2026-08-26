-- Роли приложения и права доступа.
-- Исполняется от имени app_owner (POSTGRES_USER).

\getenv app_ro_pw APP_RO_PASSWORD
\getenv app_admin_pw APP_ADMIN_PASSWORD
\getenv app_service_pw APP_SERVICE_PASSWORD

-- Рабочая read-only роль: все доменные таблицы (scope строк задаёт RLS).
CREATE ROLE app_ro LOGIN PASSWORD :'app_ro_pw';
GRANT USAGE ON SCHEMA public TO app_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_ro;

-- Роль администрации: те же доменные таблицы (scope задаёт RLS: app.role = 'admin').
CREATE ROLE app_admin LOGIN PASSWORD :'app_admin_pw';
GRANT USAGE ON SCHEMA public TO app_admin;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_admin;

-- Служебные таблицы users/query_log закрыты для обеих бизнес-ролей:
-- учётные записи и аудит доступны только служебной роли app_service.
REVOKE SELECT ON users, query_log FROM app_ro;
REVOKE SELECT ON users, query_log FROM app_admin;

-- Служебная роль приложения: auth (users) + аудит (query_log) + резолюция identity.
CREATE ROLE app_service LOGIN PASSWORD :'app_service_pw';
GRANT USAGE ON SCHEMA public TO app_service;

-- Auth и резолюция identity: чтение/запись users.
GRANT SELECT, INSERT, UPDATE ON users TO app_service;
GRANT USAGE ON SEQUENCE users_id_seq TO app_service;
-- DELETE сознательно не выдаём: деактивация учётки мягкая (is_active = FALSE).

-- Резолюция identity: роль выводится через staff.position (см. app/db).
-- Только минимальные колонки, нужные для резолюции роли; на остальные данные
-- персонала служебная роль прав не имеет.
GRANT SELECT (id, position_id) ON staff TO app_service;
GRANT SELECT (id, title) ON positions TO app_service;

-- Аудит: чтение и запись в query_log.
GRANT SELECT, INSERT ON query_log TO app_service;
GRANT USAGE ON SEQUENCE query_log_id_seq TO app_service;