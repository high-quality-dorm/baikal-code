// Локальный mock-ассистент: пока бэкенд-эндпоинт /api/v1/ask не реализован,
// фронтенд отвечает детерминированно на основе фактов засеянной базы
// (см. docs/seed.md). Интерфейс возврата совпадает с Answer/QueryMeta из
// packages/app/src/app/api/schemas.py.

const FACTS = {
  faculties: 5,
  departments: 11,
  staff: 111,
  specialties: 26,
  groups: 208,
  students: 500,
  courses: 645,
  academicRecords: 40531,
  rooms: 140,
  scheduleSlots: 3350,
  admissionPlans: 182,
  admissionStats: 182,
};

function pickSQL(question) {
  const q = question.toLowerCase();
  if (q.includes("студент") || q.includes("обуча")) {
    return "SELECT COUNT(*) AS students FROM students;";
  }
  if (q.includes("факультет") || q.includes("фак")) {
    return "SELECT name FROM faculties ORDER BY name;";
  }
  if (q.includes("направл") || q.includes("специальн")) {
    return "SELECT title FROM specialties ORDER BY title;";
  }
  if (q.includes("балл") || q.includes("успеваем") || q.includes("оценк")) {
    return "SELECT ROUND(AVG(grade), 2) AS avg_grade FROM academic_records;";
  }
  if (q.includes("преподавател") || q.includes("staff")) {
    return "SELECT COUNT(*) AS teachers FROM staff WHERE role = 'teacher';";
  }
  if (q.includes("бюджет") || q.includes("мест")) {
    return "SELECT SUM(budget_places) AS budget FROM admission_plans;";
  }
  if (q.includes("аудитор") || q.includes("комнат") || q.includes("помещен")) {
    return "SELECT COUNT(*) AS rooms FROM rooms;";
  }
  if (q.includes("расписание") || q.includes("занят") || q.includes("пары")) {
    return "SELECT COUNT(*) AS slots FROM schedule_slots;";
  }
  if (q.includes("групп")) {
    return "SELECT COUNT(*) AS groups FROM groups;";
  }
  return "SELECT COUNT(*) FROM students;";
}

function buildAnswer(question) {
  const q = question.toLowerCase();
  const rnd = (a, b) =>
    Math.floor(
      a + (b - a + 1) * ((question.length + q.charCodeAt(0)) % 17) / 17
    );

  if (q.includes("студент") || q.includes("обуча")) {
    const n = FACTS.students;
    return {
      text: `В университете обучается **${n}** студентов на **${FACTS.specialties}** направлениях подготовки. В выборку включены все факультеты (${FACTS.faculties}).`,
      row_count: 1,
    };
  }
  if (q.includes("факультет") || q.includes("фак")) {
    return {
      text: `В университете **${FACTS.faculties}** факультетов и **${FACTS.departments}** кафедр. Например: прикладная математика, экономика, информационные технологии, гуманитарные науки, естественные науки.`,
      row_count: FACTS.faculties,
    };
  }
  if (q.includes("направл") || q.includes("специальн")) {
    return {
      text: `Открыто **${FACTS.specialties}** направлений подготовки на **${FACTS.faculties}** факультетах. Среднее число направлений на факультет около ${Math.round(
        FACTS.specialties / FACTS.faculties
      )}.`,
      row_count: FACTS.specialties,
    };
  }
  if (q.includes("балл") || q.includes("успеваем") || q.includes("оценк")) {
    const avg = 4.2;
    return {
      text: `Средний балл по всем дисциплинам **${avg.toFixed(
        2
      )}** (по ${FACTS.academicRecords.toLocaleString("ru-RU")} оценкам).`,
      row_count: 1,
    };
  }
  if (q.includes("преподавател")) {
    return {
      text: `В университете **${FACTS.staff}** преподавателей и сотрудников. На каждый из ${FACTS.faculties} факультетов приходится в среднем ${Math.round(
        FACTS.staff / FACTS.faculties
      )} человек.`,
      row_count: 1,
    };
  }
  if (q.includes("бюджет") || q.includes("мест")) {
    return {
      text: `На **${FACTS.admissionPlans}** образовательных программ распределено **более 3 500 бюджетных мест** (по всем факультетам).`,
      row_count: 1,
    };
  }
  if (q.includes("аудитор") || q.includes("комнат") || q.includes("помещен")) {
    return {
      text: `Аудиторный фонд университета **${FACTS.rooms}** аудиторий. Занятия проводятся в **${FACTS.scheduleSlots.toLocaleString(
        "ru-RU"
      )}** слотов в семестре.`,
      row_count: FACTS.rooms,
    };
  }
  if (q.includes("расписание") || q.includes("занят") || q.includes("пары")) {
    return {
      text: `На текущий семестр составлено **${FACTS.scheduleSlots.toLocaleString(
        "ru-RU"
      )}** занятий в **${FACTS.rooms}** аудиториях.`,
      row_count: 1,
    };
  }
  if (q.includes("групп")) {
    return {
      text: `Сформировано **${FACTS.groups}** учебных групп по **${FACTS.specialties}** направлениям.`,
      row_count: FACTS.groups,
    };
  }
  const n = rnd(120, 400);
  return {
    text: `По запросу найдено **${n}** записей. Уточните вопрос (например, «сколько студентов», «средний балл» или «бюджетные места»), чтобы получить точный ответ.`,
    row_count: n,
  };
}

/** Детерминированный ответ, совместимый с Answer/QueryMeta. */
export function mockAnswer(question) {
  const { text, row_count } = buildAnswer(question);
  return {
    text,
    meta: {
      sql: pickSQL(question),
      row_count,
      truncated: false,
      duration_ms: 320 + (question.length % 7) * 140,
    },
  };
}

/** Матрица демо-вопросов для пустого состояния. */
export const SUGGESTED_QUESTIONS = [
  "Сколько студентов обучается в университете?",
  "Какие есть направления подготовки?",
  "Какой средний балл по университету?",
  "Сколько бюджетных мест в этом году?",
];