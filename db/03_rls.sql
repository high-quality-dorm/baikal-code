-- Row-Level Security: скоуп доступа (deny-by-default), set-based.
-- Исполняется от имени app_owner (POSTGRES_USER).
--
-- Контекст задаёт шлюз в начале транзакции двумя независимыми GUC:
--   SET LOCAL app.student_id = '<student_id>';   -- если у пользователя есть студент
--   SET LOCAL app.staff_id   = '<staff_id>';     -- если у пользователя есть сотрудник
--
-- Роль НЕ передаётся строкой и единый user_id не вводится. Доступ выводится
-- аддитивно из студенческого и/или кадрового id пользователя:
--   - app.student_id даёт доступ к своей строке students и своим marks;
--   - app.staff_id даёт скоуп по должности (teacher/head/dean/admin) через
--     отношение к staff: преподаватель -> свои занятия, зав.кафедрой -> кафедра,
--     декан -> факультет, админ -> всё.
-- Пользователь, имеющий оба id, автоматически получает объединение скоупов.
--
-- Скоупы зав.кафедрой, декана и администрации дополнительно проверяют
-- должность (position): иначе любой преподаватель, у которого заполнен
-- department_id/faculty_id, получил бы доступ к скоупам кафедры/факультета.
--
-- Гость (нет app.student_id и app.staff_id): students/marks не видны вовсе
-- (deny-by-default); общие таблицы открыты через app_ro без RLS. Публичные
-- агрегаты по студентам (численность, без PII) доступны всем через вью
-- db/04_views.sql.
--
-- Важно: после SET LOCAL в завершившейся транзакции переменная на
-- переиспользуемом соединении пула принимает значение '' (пустая строка), а не
-- NULL. Поэтому все касты ::int обёрнуты в NULLIF(..., '') — иначе ''::int упал
-- бы при следующем запросе на том же соединении (гость и т.п.).

-- ===== students =====
-- FORCE RLS на students сознательно снят (ENABLE остаётся, все политики ниже
-- действуют): владелец таблиц (app_owner) должен обходить RLS, чтобы считать
-- публичные агрегаты через вью db/04_views.sql. Для app_ro (не владельца) RLS
-- применяется всегда — доступ по строкам для гостя/студента/персонала не меняется.
-- В dev app_owner — суперпользователь (обходит RLS и так); снятие FORCE нужно
-- для прода, где app_owner на внешней БД может быть обычным владельцем.
ALTER TABLE students ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS students_deny ON students;
CREATE POLICY students_deny ON students FOR SELECT
    USING (false);

-- сам студент видит свою строку
DROP POLICY IF EXISTS students_self ON students;
CREATE POLICY students_self ON students FOR SELECT
    USING (
        students.id = NULLIF(current_setting('app.student_id', true), '')::int
    );

-- преподаватель видит студентов групп, которые ходят на его занятия
DROP POLICY IF EXISTS students_teacher ON students;
CREATE POLICY students_teacher ON students FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM lesson_group lg
            JOIN lessons l ON l.id = lg.lesson_id
            WHERE l.teacher_id = NULLIF(current_setting('app.staff_id', true), '')::int
              AND lg.group_id = students.group_id
        )
    );

-- зав. кафедрой видит студентов групп, которые ходят на занятия по предметам
-- своей кафедры. Должность проверяется явно (иначе скоуп получил бы любой
-- преподаватель кафедры). Скоуп считается через lessons (открытая таблица), а
-- не через marks: marks сам под RLS, и ссылка на него из политики students
-- вызвала бы бесконечную рекурсию политик (marks_dean ссылается на students).
DROP POLICY IF EXISTS students_head ON students;
CREATE POLICY students_head ON students FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM lesson_group lg
            JOIN lessons l ON l.id = lg.lesson_id
            JOIN subjects s ON s.id = l.subject_id
            JOIN staff st
              ON st.id = NULLIF(current_setting('app.staff_id', true), '')::int
             AND st.position_id = (SELECT id FROM positions WHERE title = 'head')
            WHERE lg.group_id = students.group_id
              AND s.department_id = st.department_id
        )
    );

-- декан видит студентов своего факультета
DROP POLICY IF EXISTS students_dean ON students;
CREATE POLICY students_dean ON students FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM groups g
            JOIN specializations sp ON sp.id = g.specialization_id
            JOIN staff st
              ON st.id = NULLIF(current_setting('app.staff_id', true), '')::int
             AND st.position_id = (SELECT id FROM positions WHERE title = 'dean')
            WHERE g.id = students.group_id
              AND sp.faculty_id = st.faculty_id
        )
    );

-- администрация видит всех
DROP POLICY IF EXISTS students_admin ON students;
CREATE POLICY students_admin ON students FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM staff
            WHERE staff.id = NULLIF(current_setting('app.staff_id', true), '')::int
              AND staff.position_id = (SELECT id FROM positions WHERE title = 'admin')
        )
    );

-- ===== marks =====
ALTER TABLE marks ENABLE ROW LEVEL SECURITY;
ALTER TABLE marks FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS marks_deny ON marks;
CREATE POLICY marks_deny ON marks FOR SELECT
    USING (false);

-- студент видит только свои оценки
DROP POLICY IF EXISTS marks_student ON marks;
CREATE POLICY marks_student ON marks FOR SELECT
    USING (
        marks.student_id = NULLIF(current_setting('app.student_id', true), '')::int
    );

-- преподаватель видит оценки по своим предметам
DROP POLICY IF EXISTS marks_teacher ON marks;
CREATE POLICY marks_teacher ON marks FOR SELECT
    USING (
        marks.subject_id IN (
            SELECT DISTINCT l.subject_id FROM lessons l
            WHERE l.teacher_id = NULLIF(current_setting('app.staff_id', true), '')::int
        )
    );

-- зав. кафедрой видит оценки по предметам своей кафедры
DROP POLICY IF EXISTS marks_head ON marks;
CREATE POLICY marks_head ON marks FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM subjects s
            JOIN staff st
              ON st.id = NULLIF(current_setting('app.staff_id', true), '')::int
             AND st.position_id = (SELECT id FROM positions WHERE title = 'head')
            WHERE s.department_id = st.department_id
              AND marks.subject_id = s.id
        )
    );

-- декан видит оценки студентов своего факультета
DROP POLICY IF EXISTS marks_dean ON marks;
CREATE POLICY marks_dean ON marks FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM students st_
            JOIN groups g ON g.id = st_.group_id
            JOIN specializations sp ON sp.id = g.specialization_id
            JOIN staff st
              ON st.id = NULLIF(current_setting('app.staff_id', true), '')::int
             AND st.position_id = (SELECT id FROM positions WHERE title = 'dean')
            WHERE st_.id = marks.student_id
              AND sp.faculty_id = st.faculty_id
        )
    );

-- администрация видит все оценки
DROP POLICY IF EXISTS marks_admin ON marks;
CREATE POLICY marks_admin ON marks FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM staff
            WHERE staff.id = NULLIF(current_setting('app.staff_id', true), '')::int
              AND staff.position_id = (SELECT id FROM positions WHERE title = 'admin')
        )
    );