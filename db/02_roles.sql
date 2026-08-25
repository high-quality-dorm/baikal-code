-- Роли приложения и права доступа.
-- Исполняется от имени app_owner (POSTGRES_USER).

-- Читаем пароли ролей из переменных окружения контейнера
\getenv app_ro_pw APP_RO_PASSWORD
\getenv app_admin_pw APP_ADMIN_PASSWORD
\getenv app_audit_pw APP_AUDIT_PASSWORD

-- Рабочая read-only роль: SELECT на все таблицы, НО без прав на PII-колонки студентов
CREATE ROLE app_ro LOGIN PASSWORD :'app_ro_pw';
GRANT USAGE ON SCHEMA public TO app_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_ro;

-- Закрываем PII-колонки для app_ro (рабочая роль не видит персональные данные).
-- Важно: сначала снимаем табличный SELECT со students, иначе column-REVOKE не действует
-- (табличная привилегия перекрывает колоночную). Затем даём SELECT только на безопасные колонки.
REVOKE SELECT ON students FROM app_ro;
GRANT SELECT (student_id, specialty_id, group_id, admission_year, status_id) ON students TO app_ro;

-- app_ro не должен читать служебные таблицы (маппинг пользователей и журнал аудита)
REVOKE SELECT ON users, query_log FROM app_ro;

-- Администрация: как app_ro + права на PII-колонки студентов
CREATE ROLE app_admin LOGIN PASSWORD :'app_admin_pw';
GRANT USAGE ON SCHEMA public TO app_admin;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_admin;

-- Аудит: чтение и запись в query_log + резолюция identity для шлюза.
CREATE ROLE app_audit LOGIN PASSWORD :'app_audit_pw';
GRANT USAGE ON SCHEMA public TO app_audit;
GRANT SELECT, INSERT ON query_log TO app_audit;
-- USAGE на последовательность id (BIGSERIAL), иначе INSERT без id не сработает
GRANT USAGE ON SEQUENCE query_log_id_seq TO app_audit;
-- Шлюз резолвит users.id -> internal_id для RLS-контекста. Только две колонки:
-- не password_hash/email/external_id и т.п. (см. ADR 21).
GRANT SELECT (id, internal_id) ON users TO app_audit;

-- Закрываем PII-колонки для app_ro (рабочая роль не видит персональные данные)
REVOKE SELECT (name, surname, patronymic, passport) ON students FROM app_ro;
