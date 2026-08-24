-- Row-Level Security: ролевое ограничение доступа к строкам.
-- Исполняется от имени app_owner (POSTGRES_USER).

-- Контекст RLS устанавливается приложением в начале транзакции:
--   SET LOCAL app.role = 'student' | 'teacher' | 'admin';
--   SET LOCAL app.user_id = '<internal_id>';
-- Значения ролей: applicant | student | teacher | admin.

-- ===== students =====
ALTER TABLE students ENABLE ROW LEVEL SECURITY;
ALTER TABLE students FORCE ROW LEVEL SECURITY;

-- deny by default: без установленного контекста ничего не видно
DROP POLICY IF EXISTS students_deny_default ON students;
CREATE POLICY students_deny_default ON students FOR SELECT
    USING (false);

-- администрация видит всех студентов
DROP POLICY IF EXISTS students_admin ON students;
CREATE POLICY students_admin ON students FOR SELECT
    USING (current_setting('app.role', true) = 'admin');

-- студент видит только свою строку
DROP POLICY IF EXISTS students_self ON students;
CREATE POLICY students_self ON students FOR SELECT
    USING (
        current_setting('app.role', true) = 'student'
        AND current_setting('app.user_id', true) = student_id::text
    );

-- ===== academic_records =====
ALTER TABLE academic_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE academic_records FORCE ROW LEVEL SECURITY;

-- deny by default
DROP POLICY IF EXISTS academic_records_deny_default ON academic_records;
CREATE POLICY academic_records_deny_default ON academic_records FOR SELECT
    USING (false);

-- студент видит только свои оценки
DROP POLICY IF EXISTS academic_records_student ON academic_records;
CREATE POLICY academic_records_student ON academic_records FOR SELECT
    USING (
        current_setting('app.role', true) = 'student'
        AND current_setting('app.user_id', true) = student_id::text
    );

-- преподаватель видит оценки только по своим курсам
DROP POLICY IF EXISTS academic_records_teacher ON academic_records;
CREATE POLICY academic_records_teacher ON academic_records FOR SELECT
    USING (
        current_setting('app.role', true) = 'teacher'
        AND EXISTS (
            SELECT 1
            FROM course_instructors ci
            WHERE ci.course_id = academic_records.course_id
              AND ci.staff_id = current_setting('app.user_id', true)::int
        )
    );

-- администрация видит все оценки
DROP POLICY IF EXISTS academic_records_admin ON academic_records;
CREATE POLICY academic_records_admin ON academic_records FOR SELECT
    USING (current_setting('app.role', true) = 'admin');
