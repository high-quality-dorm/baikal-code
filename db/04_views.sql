-- Публичные агрегаты по студентам: только численность, без персональных данных.
-- Исполняется от имени app_owner (POSTGRES_USER) после 01–03.
--
-- Механизм: вью принадлежат app_owner (владельцу таблиц). По умолчанию
-- (security_invoker = false) тело вью исполняется с правами владельца, а RLS
-- применяются к нему как к владельцу. С `students` снят FORCE RLS (см.
-- 03_rls.sql) — владелец обходит RLS и агрегирует всех студентов. Рабочая роль
-- app_ro напрямую в students/marks по-прежнему ограничена RLS (она не владелец);
-- через эти вью она видит только фиксированные счётчики.
--
-- Гранты — только на сами вью (НЕ `GRANT SELECT ON ALL TABLES`: это вернуло бы
-- app_ro доступ к users/query_log, отозванный в 02_roles.sql).

-- 1. Всего студентов
CREATE VIEW v_students_total AS
    SELECT count(*) AS students
      FROM students;

-- 2. По факультетам
CREATE VIEW v_students_by_faculty AS
    SELECT f.id AS faculty_id,
           f.title AS faculty_title,
           count(*) AS students
      FROM students s
      JOIN groups g ON g.id = s.group_id
      JOIN specializations sp ON sp.id = g.specialization_id
      JOIN faculties f ON f.id = sp.faculty_id
     GROUP BY f.id, f.title;

-- 3. По направлениям подготовки
CREATE VIEW v_students_by_specialization AS
    SELECT sp.id AS specialization_id,
           sp.code AS code,
           sp.title AS specialization_title,
           f.title AS faculty_title,
           count(*) AS students
      FROM students s
      JOIN groups g ON g.id = s.group_id
      JOIN specializations sp ON sp.id = g.specialization_id
      JOIN faculties f ON f.id = sp.faculty_id
     GROUP BY sp.id, sp.code, sp.title, f.title;

-- 4. По учебным группам
CREATE VIEW v_students_by_group AS
    SELECT g.id AS group_id,
           g.title AS group_title,
           sp.title AS specialization_title,
           g.admission_year,
           count(*) AS students
      FROM students s
      JOIN groups g ON g.id = s.group_id
      JOIN specializations sp ON sp.id = g.specialization_id
     GROUP BY g.id, g.title, sp.title, g.admission_year;

-- 5. По статусам
CREATE VIEW v_students_by_status AS
    SELECT st.id AS status_id,
           st.title AS status_title,
           st.is_studying,
           count(*) AS students
      FROM students s
      JOIN student_statuses st ON st.id = s.status_id
     GROUP BY st.id, st.title, st.is_studying;

-- 6. По году поступления
CREATE VIEW v_students_by_admission_year AS
    SELECT s.admission_year,
           count(*) AS students
      FROM students s
     GROUP BY s.admission_year;

-- 7. Отчисленные (статистика отчислений без ФИО): по году поступления и факультету
CREATE VIEW v_students_expelled AS
    SELECT s.admission_year,
           f.id AS faculty_id,
           f.title AS faculty_title,
           count(*) AS students
      FROM students s
      JOIN groups g ON g.id = s.group_id
      JOIN specializations sp ON sp.id = g.specialization_id
      JOIN faculties f ON f.id = sp.faculty_id
      JOIN student_statuses st ON st.id = s.status_id
     WHERE st.title = 'Отчислен'
     GROUP BY s.admission_year, f.id, f.title;

-- Рабочей роли — SELECT на сами вью (поимённо, см. комментарий выше)
GRANT SELECT ON v_students_total TO app_ro;
GRANT SELECT ON v_students_by_faculty TO app_ro;
GRANT SELECT ON v_students_by_specialization TO app_ro;
GRANT SELECT ON v_students_by_group TO app_ro;
GRANT SELECT ON v_students_by_status TO app_ro;
GRANT SELECT ON v_students_by_admission_year TO app_ro;
GRANT SELECT ON v_students_expelled TO app_ro;