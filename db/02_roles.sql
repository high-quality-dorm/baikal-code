-- Роли приложения и права доступа.
-- Исполняется от имени app_owner (POSTGRES_USER).
--
-- Модель доступа — set-based (без роли строкой и без единого user_id):
-- шлюз ставит в транзакции GUC app.student_id и/или app.staff_id, а RLS
-- (03_rls.sql) выводит скоуп аддитивно из этих id. Поэтому нужна всего одна
-- бизнес-роль app_ro (гость и все роли ходят через неё), а «кто сколько видит»
-- определяет RLS.

\getenv app_ro_pw APP_RO_PASSWORD
\getenv app_service_pw APP_SERVICE_PASSWORD

-- Рабочая read-only роль: все доменные таблицы (scope строк задаёт RLS).
CREATE ROLE app_ro LOGIN PASSWORD :'app_ro_pw';
GRANT USAGE ON SCHEMA public TO app_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_ro;

-- Служебные таблицы users/query_log закрыты для бизнес-роли:
-- учётные записи и аудит доступны только служебной роли app_service.
REVOKE SELECT ON users, query_log FROM app_ro;

-- Служебная роль приложения: auth (users) + аудит (query_log) + резолюция identity.
CREATE ROLE app_service LOGIN PASSWORD :'app_service_pw';
GRANT USAGE ON SCHEMA public TO app_service;

-- Auth: чтение/запись users (без DELETE — деактивация мягкая, is_active = FALSE).
GRANT SELECT, INSERT, UPDATE ON users TO app_service;
GRANT USAGE ON SEQUENCE users_id_seq TO app_service;

-- Резолюция identity: из users берём student_id/staff_id и роль персонала через
-- staff.position. Роль выводится динамически; на остальные данные персонала
-- служебная роль прав не имеет (только минимальные колонки для резолюции).
GRANT SELECT (id, student_id, staff_id, email, password_hash, is_active) ON users TO app_service;
GRANT SELECT (id, faculty_id, department_id, position_id) ON staff TO app_service;
GRANT SELECT (id, title) ON positions TO app_service;

-- Аудит: чтение и запись в query_log.
GRANT SELECT, INSERT ON query_log TO app_service;
GRANT USAGE ON SEQUENCE query_log_id_seq TO app_service;
