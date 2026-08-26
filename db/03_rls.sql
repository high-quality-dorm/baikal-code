-- Row-Level Security: роли и скоуп доступа (deny-by-default).
-- Исполняется от имени app_owner (POSTGRES_USER).
--
-- Контекст задаёт шлюз в начале транзакции:
--   SET LOCAL app.role   = 'student' | 'teacher' | 'head' | 'dean' | 'admin';
--   SET LOCAL app.user_id = '<student_id | staff_id>';
-- Без контекста строк не видно (deny-by-default).
--
-- Важно: после SET LOCAL app.user_id в завершившейся транзакции переменная на
-- переиспользуемом соединении пула принимает значение '' (пустая строка), а не
-- NULL. Поэтому все касты ::int обёрнуты в NULLIF(..., '') — иначе ''::int
-- упал бы при следующем запросе на том же соединении (гость и т.п.).

-- ===== students =====
ALTER TABLE students ENABLE ROW LEVEL SECURITY;
ALTER TABLE students FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS students_deny ON students;
CREATE POLICY students_deny ON students FOR SELECT
    USING (false);

-- студент видит только свою строку
DROP POLICY IF EXISTS students_self ON students;
CREATE POLICY students_self ON students FOR SELECT
    USING (
        current_setting('app.role', true) = 'student'
        AND current_setting('app.user_id', true) = students.id::text
    );

-- преподаватель видит студентов групп, которые ходят на его занятия
DROP POLICY IF EXISTS students_teacher ON students;
CREATE POLICY students_teacher ON students FOR SELECT
    USING (
        current_setting('app.role', true) = 'teacher'
        AND EXISTS (
            SELECT 1 FROM lesson_group lg
            JOIN lessons l ON l.id = lg.lesson_id
            WHERE l.teacher_id = NULLIF(current_setting('app.user_id', true), '')::int
              AND lg.group_id = students.group_id
        )
    );

-- зав. кафедрой видит студентов групп, которые ходят на занятия по предметам
-- своей кафедры. Скоуп считается через lessons (открытая таблица), а не через
-- marks: marks сам под RLS, и ссылка на него из политики students вызвала бы
-- бесконечную рекурсию политик (marks_dean ссылается на students).
DROP POLICY IF EXISTS students_head ON students;
CREATE POLICY students_head ON students FOR SELECT
    USING (
        current_setting('app.role', true) = 'head'
        AND EXISTS (
            SELECT 1 FROM lesson_group lg
            JOIN lessons l ON l.id = lg.lesson_id
            JOIN subjects s ON s.id = l.subject_id
            WHERE lg.group_id = students.group_id
              AND s.department_id = (
                  SELECT department_id FROM staff
                  WHERE staff.id = NULLIF(current_setting('app.user_id', true), '')::int
              )
        )
    );

-- декан видит студентов своего факультета
DROP POLICY IF EXISTS students_dean ON students;
CREATE POLICY students_dean ON students FOR SELECT
    USING (
        current_setting('app.role', true) = 'dean'
        AND EXISTS (
            SELECT 1 FROM groups g
            JOIN specializations sp ON sp.id = g.specialization_id
            WHERE g.id = students.group_id
              AND sp.faculty_id = (
                  SELECT faculty_id FROM staff
                  WHERE staff.id = NULLIF(current_setting('app.user_id', true), '')::int
              )
        )
    );

-- администрация видит всех
DROP POLICY IF EXISTS students_admin ON students;
CREATE POLICY students_admin ON students FOR SELECT
    USING (current_setting('app.role', true) = 'admin');

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
        current_setting('app.role', true) = 'student'
        AND marks.student_id = NULLIF(current_setting('app.user_id', true), '')::int
    );

-- преподаватель видит оценки по своим предметам
DROP POLICY IF EXISTS marks_teacher ON marks;
CREATE POLICY marks_teacher ON marks FOR SELECT
    USING (
        current_setting('app.role', true) = 'teacher'
        AND marks.subject_id IN (
            SELECT DISTINCT l.subject_id FROM lessons l
            WHERE l.teacher_id = NULLIF(current_setting('app.user_id', true), '')::int
        )
    );

-- зав. кафедрой видит оценки по предметам своей кафедры
DROP POLICY IF EXISTS marks_head ON marks;
CREATE POLICY marks_head ON marks FOR SELECT
    USING (
        current_setting('app.role', true) = 'head'
        AND marks.subject_id IN (
            SELECT s.id FROM subjects s
            WHERE s.department_id = (
                SELECT department_id FROM staff
                WHERE staff.id = NULLIF(current_setting('app.user_id', true), '')::int
            )
        )
    );

-- декан видит оценки студентов своего факультета
DROP POLICY IF EXISTS marks_dean ON marks;
CREATE POLICY marks_dean ON marks FOR SELECT
    USING (
        current_setting('app.role', true) = 'dean'
        AND EXISTS (
            SELECT 1 FROM students st
            JOIN groups g ON g.id = st.group_id
            JOIN specializations sp ON sp.id = g.specialization_id
            WHERE st.id = marks.student_id
              AND sp.faculty_id = (
                  SELECT faculty_id FROM staff
                  WHERE staff.id = NULLIF(current_setting('app.user_id', true), '')::int
              )
        )
    );

-- администрация видит все оценки
DROP POLICY IF EXISTS marks_admin ON marks;
CREATE POLICY marks_admin ON marks FOR SELECT
    USING (current_setting('app.role', true) = 'admin');