-- Схема базы данных университета (Baikal v2).
-- Исполняется от имени app_owner (POSTGRES_USER) при первом старте контейнера.

-- 1. Здания
CREATE TABLE buildings (
    id SERIAL PRIMARY KEY,
    title VARCHAR(100) NOT NULL
);

-- 2. Факультеты (dean_id добавляется ALTER'ом ниже — ссылается на staff)
CREATE TABLE faculties (
    id SERIAL PRIMARY KEY,
    title VARCHAR(100) NOT NULL UNIQUE,
    dean_id INT
);

-- 3. Кафедры (head_id добавляется ALTER'ом ниже)
CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    faculty_id INT NOT NULL REFERENCES faculties(id),
    head_id INT
);

-- 4. Направления подготовки
CREATE TABLE specializations (
    id SERIAL PRIMARY KEY,
    faculty_id INT NOT NULL REFERENCES faculties(id),
    code VARCHAR(20) NOT NULL UNIQUE,
    title VARCHAR(150) NOT NULL
);

-- 5. Учебные группы
CREATE TABLE groups (
    id SERIAL PRIMARY KEY,
    specialization_id INT NOT NULL REFERENCES specializations(id),
    title VARCHAR(50) NOT NULL,
    admission_year INT NOT NULL,
    UNIQUE (specialization_id, admission_year, title)
);

-- 6. Статусы студентов (is_studying — «учится сейчас» да/нет)
CREATE TABLE student_statuses (
    id SERIAL PRIMARY KEY,
    title VARCHAR(50) NOT NULL UNIQUE,
    is_studying BOOLEAN NOT NULL
);

-- 7. Студенты (name/surname/patronymic — PII, доступ ограничен RLS)
CREATE TABLE students (
    id SERIAL PRIMARY KEY,
    group_id INT REFERENCES groups(id),
    status_id INT REFERENCES student_statuses(id),
    admission_year INT NOT NULL,
    name VARCHAR(30) NOT NULL,
    surname VARCHAR(30) NOT NULL,
    patronymic VARCHAR(30)
);

-- 8. Должности персонала (teacher | head | dean | admin)
CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    title VARCHAR(20) NOT NULL UNIQUE
);

-- 9. Сотрудники и преподаватели (ФИО — публично, не PII)
CREATE TABLE staff (
    id SERIAL PRIMARY KEY,
    faculty_id INT REFERENCES faculties(id),
    department_id INT REFERENCES departments(id),
    position_id INT NOT NULL REFERENCES positions(id),
    name VARCHAR(30) NOT NULL,
    surname VARCHAR(30) NOT NULL,
    patronymic VARCHAR(30)
);

-- 10. Дисциплины (закреплены за кафедрой)
CREATE TABLE subjects (
    id SERIAL PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    department_id INT REFERENCES departments(id)
);

-- 11. Семестры (учебные годы); «текущий семестр» определяется по датам
CREATE TABLE terms (
    id SERIAL PRIMARY KEY,
    year INT NOT NULL,
    semester INT NOT NULL CHECK (semester IN (1, 2)),
    date_start DATE NOT NULL,
    date_end DATE NOT NULL,
    UNIQUE (year, semester)
);

-- 12. Аудитории
CREATE TABLE classrooms (
    id SERIAL PRIMARY KEY,
    building_id INT NOT NULL REFERENCES buildings(id),
    number VARCHAR(20) NOT NULL,
    capacity INT NOT NULL DEFAULT 0
);

-- 13. Занятия
CREATE TABLE lessons (
    id SERIAL PRIMARY KEY,
    subject_id INT NOT NULL REFERENCES subjects(id),
    classroom_id INT NOT NULL REFERENCES classrooms(id),
    teacher_id INT NOT NULL REFERENCES staff(id),
    term_id INT NOT NULL REFERENCES terms(id),
    weekday INT NOT NULL CHECK (weekday BETWEEN 1 AND 7),
    period INT NOT NULL CHECK (period BETWEEN 1 AND 8)
);

-- 14. Занятия ↔ группы (many-to-many: лекции идут для нескольких групп)
CREATE TABLE lesson_group (
    lesson_id INT NOT NULL REFERENCES lessons(id),
    group_id INT NOT NULL REFERENCES groups(id),
    PRIMARY KEY (lesson_id, group_id)
);

-- 15. Успеваемость (оценка 0-5; NULL = не аттестован)
CREATE TABLE marks (
    id SERIAL PRIMARY KEY,
    student_id INT NOT NULL REFERENCES students(id),
    subject_id INT NOT NULL REFERENCES subjects(id),
    term_id INT NOT NULL REFERENCES terms(id),
    grade NUMERIC(3, 2) CHECK (grade BETWEEN 0 AND 5),
    has_debt BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (student_id, subject_id, term_id)
);

-- 16. Пользователи платформы (auth + маппинг на студента/сотрудника)
-- student_id/staff_id — необязательные «расширители» доступа: дают доступ к
-- данным студента/сотрудника соответственно. Пользователь без обоих видит
-- только общую информацию (как гость). Роль строкой не хранится — она
-- выводится динамически из staff.position и/или наличия student_id.
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    student_id INT REFERENCES students(id),
    staff_id INT REFERENCES staff(id),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- 17. Приёмные кампании (по годам)
CREATE TABLE admission_campaigns (
    id SERIAL PRIMARY KEY,
    year INT NOT NULL UNIQUE
);

-- 18. Приёмные комиссии (по факультету на кампанию)
CREATE TABLE admission_committees (
    id SERIAL PRIMARY KEY,
    campaign_id INT NOT NULL REFERENCES admission_campaigns(id),
    faculty_id INT NOT NULL REFERENCES faculties(id),
    head_staff_id INT REFERENCES staff(id),
    location VARCHAR(200),
    phone VARCHAR(50),
    email VARCHAR(255),
    working_hours VARCHAR(100)
);

-- 19. Состав приёмных комиссий
CREATE TABLE admission_committee_members (
    committee_id INT NOT NULL REFERENCES admission_committees(id),
    staff_id INT NOT NULL REFERENCES staff(id),
    PRIMARY KEY (committee_id, staff_id)
);

-- 20. Контрольные цифры приёма
CREATE TABLE admission_plans (
    id SERIAL PRIMARY KEY,
    campaign_id INT NOT NULL REFERENCES admission_campaigns(id),
    specialization_id INT NOT NULL REFERENCES specializations(id),
    budget_places INT NOT NULL DEFAULT 0,
    paid_places INT NOT NULL DEFAULT 0,
    application_deadline DATE,
    UNIQUE (campaign_id, specialization_id)
);

-- 21. Фактическая статистика приёма
CREATE TABLE admission_stats (
    id SERIAL PRIMARY KEY,
    campaign_id INT NOT NULL REFERENCES admission_campaigns(id),
    specialization_id INT NOT NULL REFERENCES specializations(id),
    applications INT NOT NULL DEFAULT 0,
    enrolled INT NOT NULL DEFAULT 0,
    passing_score NUMERIC(3, 2) CHECK (passing_score BETWEEN 0 AND 5),
    avg_score NUMERIC(3, 2) CHECK (avg_score BETWEEN 0 AND 5),
    UNIQUE (campaign_id, specialization_id)
);

-- 22. Журнал аудита шлюза (служебная таблица, не в домене)
CREATE TABLE query_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    role VARCHAR(20),
    user_id VARCHAR(100),
    sql_query TEXT,
    status VARCHAR(20),
    row_count INT,
    error TEXT,
    duration_ms NUMERIC(10, 3)
);

-- Обратные ссылки на staff (после создания всех таблиц)
ALTER TABLE faculties
    ADD CONSTRAINT fk_faculties_dean FOREIGN KEY (dean_id) REFERENCES staff(id);
ALTER TABLE departments
    ADD CONSTRAINT fk_departments_head FOREIGN KEY (head_id) REFERENCES staff(id);

-- Индексы по внешним ключам (нужны для RLS-join'ов)
CREATE INDEX idx_departments_faculty ON departments(faculty_id);
CREATE INDEX idx_specializations_faculty ON specializations(faculty_id);
CREATE INDEX idx_groups_specialization ON groups(specialization_id);
CREATE INDEX idx_students_group ON students(group_id);
CREATE INDEX idx_students_status ON students(status_id);
CREATE INDEX idx_staff_faculty ON staff(faculty_id);
CREATE INDEX idx_staff_department ON staff(department_id);
CREATE INDEX idx_staff_position ON staff(position_id);
CREATE INDEX idx_subjects_department ON subjects(department_id);
CREATE INDEX idx_lessons_subject ON lessons(subject_id);
CREATE INDEX idx_lessons_classroom ON lessons(classroom_id);
CREATE INDEX idx_lessons_teacher ON lessons(teacher_id);
CREATE INDEX idx_lessons_term ON lessons(term_id);
CREATE INDEX idx_lesson_group_group ON lesson_group(group_id);
CREATE INDEX idx_marks_student ON marks(student_id);
CREATE INDEX idx_marks_subject ON marks(subject_id);
CREATE INDEX idx_marks_term ON marks(term_id);
CREATE INDEX idx_admission_committees_campaign ON admission_committees(campaign_id);
CREATE INDEX idx_admission_committees_faculty ON admission_committees(faculty_id);
CREATE INDEX idx_admission_committee_members_staff ON admission_committee_members(staff_id);
CREATE INDEX idx_admission_plans_campaign ON admission_plans(campaign_id);
CREATE INDEX idx_admission_plans_specialization ON admission_plans(specialization_id);
CREATE INDEX idx_admission_stats_campaign ON admission_stats(campaign_id);
CREATE INDEX idx_admission_stats_specialization ON admission_stats(specialization_id);
CREATE INDEX idx_users_student ON users(student_id);
CREATE INDEX idx_users_staff ON users(staff_id);