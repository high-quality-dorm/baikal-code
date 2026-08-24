-- Схема базы данных университета.
-- Исполняется от имени app_owner (POSTGRES_USER) при первом старте контейнера.

-- 1. Факультеты (dean_id добавлен через ALTER ниже, т.к. ссылается на staff)
CREATE TABLE faculties (
    faculty_id SERIAL PRIMARY KEY,
    title VARCHAR(100) NOT NULL UNIQUE,
    dean_id INT
);

-- 2. Кафедры (head_id добавлен через ALTER ниже)
CREATE TABLE departments (
    department_id SERIAL PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    faculty_id INT NOT NULL REFERENCES faculties(faculty_id),
    head_id INT
);

-- 3. Роли сотрудников
CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    title VARCHAR(50) NOT NULL
);

-- 4. Сотрудники / преподаватели
CREATE TABLE staff (
    staff_id SERIAL PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    role_id INT REFERENCES roles(id),
    department_id INT REFERENCES departments(department_id)
);

-- 5. Направления подготовки
CREATE TABLE specialties (
    specialty_id SERIAL PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    title VARCHAR(150) NOT NULL,
    faculty_id INT NOT NULL REFERENCES faculties(faculty_id),
    total_semesters INT NOT NULL DEFAULT 8
);

-- 6. Справочник статусов студентов
CREATE TABLE student_statuses (
    status_id SERIAL PRIMARY KEY,
    title VARCHAR(50) NOT NULL UNIQUE
);

-- 7. Учебные группы
CREATE TABLE groups (
    group_id SERIAL PRIMARY KEY,
    title VARCHAR(50) NOT NULL,
    specialty_id INT NOT NULL REFERENCES specialties(specialty_id),
    admission_year INT NOT NULL
);

-- 8. Профиль студента (name/surname/patronymic/passport — персональные данные)
CREATE TABLE students (
    student_id SERIAL PRIMARY KEY,
    name VARCHAR(30) NOT NULL,
    surname VARCHAR(30) NOT NULL,
    patronymic VARCHAR(30),
    passport VARCHAR(20) NOT NULL UNIQUE,
    specialty_id INT NOT NULL REFERENCES specialties(specialty_id),
    group_id INT REFERENCES groups(group_id),
    admission_year INT NOT NULL,
    status_id INT REFERENCES student_statuses(status_id)
);

-- 9. Учебные дисциплины
CREATE TABLE courses (
    course_id SERIAL PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    department_id INT REFERENCES departments(department_id),
    semester INT NOT NULL,
    lecture_hours INT DEFAULT 0
);

-- 10. Назначение преподавателей на курсы
CREATE TABLE course_instructors (
    course_id INT REFERENCES courses(course_id),
    staff_id INT REFERENCES staff(staff_id),
    PRIMARY KEY (course_id, staff_id)
);

-- 11. Успеваемость студентов
CREATE TABLE academic_records (
    record_id SERIAL PRIMARY KEY,
    student_id INT REFERENCES students(student_id),
    course_id INT REFERENCES courses(course_id),
    grade NUMERIC(3, 2),
    has_debt BOOLEAN DEFAULT FALSE,
    semester INT NOT NULL
);

-- 12. Аудиторный фонд
CREATE TABLE rooms (
    room_id SERIAL PRIMARY KEY,
    building VARCHAR(50) NOT NULL,
    number VARCHAR(20) NOT NULL,
    capacity INT NOT NULL DEFAULT 0
);

-- 13. Расписание занятий
CREATE TABLE schedule_slots (
    slot_id SERIAL PRIMARY KEY,
    course_id INT NOT NULL REFERENCES courses(course_id),
    group_id INT REFERENCES groups(group_id),
    room_id INT REFERENCES rooms(room_id),
    weekday INT NOT NULL CHECK (weekday BETWEEN 1 AND 7),
    period INT NOT NULL CHECK (period BETWEEN 1 AND 8)
);

-- 14. Контрольные цифры приёма по годам
CREATE TABLE admission_plans (
    plan_id SERIAL PRIMARY KEY,
    year INT NOT NULL,
    specialty_id INT NOT NULL REFERENCES specialties(specialty_id),
    budget_places INT NOT NULL DEFAULT 0,
    paid_places INT NOT NULL DEFAULT 0,
    application_deadline DATE
);

-- 15. Фактическая статистика приёма по годам
CREATE TABLE admission_stats (
    stat_id SERIAL PRIMARY KEY,
    year INT NOT NULL,
    specialty_id INT NOT NULL REFERENCES specialties(specialty_id),
    applications INT NOT NULL DEFAULT 0,
    enrolled INT NOT NULL DEFAULT 0,
    passing_score NUMERIC(3, 2),
    avg_score NUMERIC(3, 2)
);

-- 16. Учётные записи пользователей (логин/пароль для auth + маппинг на внутренние id)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) UNIQUE,              -- логин (может быть NULL на время перехода)
    password_hash VARCHAR(255),             -- bcrypt-хэш пароля
    role VARCHAR(20) NOT NULL,              -- applicant | student | teacher | admin
    internal_id INT,                        -- student_id или staff_id
    display_name VARCHAR(150),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- 17. Журнал аудита запросов
CREATE TABLE query_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    role VARCHAR(20) NOT NULL,
    user_id VARCHAR(100),
    question TEXT,
    sql_query TEXT,
    status VARCHAR(20) NOT NULL,
    row_count INT,
    error TEXT,
    duration_ms NUMERIC(10, 3)
);

-- Обратные ссылки на staff (после создания всех таблиц)
ALTER TABLE faculties
    ADD CONSTRAINT fk_faculties_dean FOREIGN KEY (dean_id) REFERENCES staff(staff_id);
ALTER TABLE departments
    ADD CONSTRAINT fk_departments_head FOREIGN KEY (head_id) REFERENCES staff(staff_id);

-- Индексы по внешним ключам
CREATE INDEX idx_departments_faculty ON departments(faculty_id);
CREATE INDEX idx_staff_department ON staff(department_id);
CREATE INDEX idx_specialties_faculty ON specialties(faculty_id);
CREATE INDEX idx_groups_specialty ON groups(specialty_id);
CREATE INDEX idx_students_specialty ON students(specialty_id);
CREATE INDEX idx_students_group ON students(group_id);
CREATE INDEX idx_courses_department ON courses(department_id);
CREATE INDEX idx_course_instructors_staff ON course_instructors(staff_id);
CREATE INDEX idx_academic_records_student ON academic_records(student_id);
CREATE INDEX idx_academic_records_course ON academic_records(course_id);
CREATE INDEX idx_academic_records_semester ON academic_records(semester);
CREATE INDEX idx_schedule_slots_course ON schedule_slots(course_id);
CREATE INDEX idx_schedule_slots_group ON schedule_slots(group_id);
CREATE INDEX idx_admission_plans_specialty ON admission_plans(specialty_id);
CREATE INDEX idx_admission_stats_specialty ON admission_stats(specialty_id);
