import { Link } from "react-router-dom";
import SiteHeader from "../components/SiteHeader.jsx";
import SiteFooter from "../components/SiteFooter.jsx";
import Reveal from "../components/Reveal.jsx";
import {
  IconShield,
  IconLock,
  IconSparkles,
  IconGauge,
  IconDatabase,
  IconClipboard,
  IconArrowRight,
  IconBook,
  IconGraduation,
  IconBuilding,
  IconUsers,
} from "../components/icons.jsx";

const FEATURES = [
  {
    icon: IconShield,
    title: "Единственный шлюз",
    text: "Приложение никогда не обращается к базе напрямую — весь доступ идёт только через безопасный шлюз db_mcp.",
  },
  {
    icon: IconLock,
    title: "Роли и RLS",
    text: "Каждая роль видит только свои данные. Студент — свою успеваемость, преподаватель — свои курсы, администрация — всё.",
  },
  {
    icon: IconDatabase,
    title: "Агрегированные данные",
    text: "Персональные данные студентов недоступны — ответы всегда обезличенные или агрегированные.",
  },
  {
    icon: IconClipboard,
    title: "Аудит запросов",
    text: "Каждый запрос фиксируется в журнале. Всегда можно ответить на вопрос «кто что спрашивал».",
  },
  {
    icon: IconGauge,
    title: "Быстрые ответы",
    text: "Валидация, маскирование схемы и гарантированный лимит строк — ответ приходит быстро и безопасно.",
  },
  {
    icon: IconSparkles,
    title: "Вопрос по-человечески",
    text: "Без SQL. Опишите, что хотите узнать, — ассистент сам построит проверенный запрос.",
  },
];

const STEPS = [
  {
    icon: IconSparkles,
    num: "01",
    title: "Вопрос",
    text: "Вы задаёте вопрос на естественном языке.",
  },
  {
    icon: IconDatabase,
    num: "02",
    title: "SQL",
    text: "Ассистент строит запрос по маскированной схеме под вашу роль.",
  },
  {
    icon: IconShield,
    num: "03",
    title: "Проверка",
    text: "Запрос валидируется и исполняется только через защищённый шлюз.",
  },
  {
    icon: IconClipboard,
    num: "04",
    title: "Ответ",
    text: "Вы получаете понятный ответ с метаданными и аудитом.",
  },
];

const ROLES = [
  {
    icon: IconBook,
    tag: "role-card__tag",
    tagStyle: { background: "var(--color-secondary)", color: "var(--color-on-primary)" },
    title: "Абитуриент",
    items: [
      "Направления подготовки",
      "Бюджетные и платные места",
      "Статистика приёма прошлых лет",
      "Проходные баллы",
    ],
  },
  {
    icon: IconGraduation,
    tagStyle: { background: "var(--color-primary)", color: "var(--color-on-primary)" },
    title: "Студент",
    items: [
      "Собственная успеваемость",
      "Средний балл за семестр",
      "Академические задолженности",
      "Расписание занятий",
    ],
  },
  {
    icon: IconUsers,
    tagStyle: { background: "var(--color-accent)", color: "var(--color-on-accent)" },
    title: "Преподаватель",
    items: [
      "Список своих дисциплин",
      "Средний балл по дисциплине",
      "Процент неаттестованных",
      "Учебная нагрузка",
    ],
  },
  {
    icon: IconBuilding,
    tagStyle: { background: "var(--color-foreground)", color: "var(--color-background)" },
    title: "Администрация",
    items: [
      "Численность по факультетам",
      "Статистика приёма",
      "Заполняемость аудиторий",
      "Нагрузка преподавателей",
    ],
  },
];

function WaveDivider() {
  return (
    <svg className="wave" viewBox="0 0 1200 60" preserveAspectRatio="none" aria-hidden="true">
      <path d="M0 40c150-25 300-25 450 0s300 25 450 0 250-18 300 2v18H0z" />
    </svg>
  );
}

export default function Landing() {
  return (
    <>
      <SiteHeader />

      <section className="hero">
        <div className="container hero__inner">
          <div className="hero__content">
            <Reveal>
              <span className="hero__badge">
                <IconSparkles width={15} height={15} />
                Безопасный text-to-SQL
              </span>
            </Reveal>
            <Reveal delay={80}>
              <h1 className="hero__title">
                Спросите базу данных <em>на человеческом языке</em>
              </h1>
            </Reveal>
            <Reveal delay={160}>
              <p className="hero__subtitle">
                Baikal превращает ваш вопрос в проверенный SQL-запрос к базе
                университета и возвращает понятный ответ — с ролями,
                маскированием личных данных и аудитом.
              </p>
            </Reveal>
            <Reveal delay={240}>
              <div className="hero__actions">
                <Link to="/chat" className="btn btn-primary btn-lg">
                  Открыть чат
                  <IconArrowRight width={18} height={18} />
                </Link>
                <a href="/#how-it-works" className="btn btn-ghost btn-lg">
                  Как это работает
                </a>
              </div>
            </Reveal>
            <Reveal delay={320}>
              <div className="hero__trust">
                <span>
                  <IconShield width={15} height={15} /> Роли и RLS
                </span>
                <span>
                  <IconLock width={15} height={15} /> PII защищено
                </span>
                <span>
                  <IconClipboard width={15} height={15} /> Аудит запросов
                </span>
              </div>
            </Reveal>
          </div>

          <Reveal delay={200} className="hero-demo">
            <div className="hero-demo__card">
              <div className="hero-demo__bar">
                <span className="hero-demo__dot hero-demo__dot--a" />
                <span className="hero-demo__dot hero-demo__dot--b" />
                <span className="hero-demo__dot hero-demo__dot--c" />
              </div>
              <div className="hero-demo__body">
                <div className="hero-demo__question">
                  Сколько студентов обучается в университете?
                </div>
                <div className="hero-demo__answer">
                  В университете обучается <strong>500</strong> студентов на{" "}
                  <strong>26</strong> направлениях подготовки.
                  <div className="hero-demo__meta">
                    SQL: <code>SELECT COUNT(*) FROM students</code> · 1 строка ·
                    420 ms
                  </div>
                </div>
              </div>
            </div>
          </Reveal>
        </div>
        <WaveDivider />
      </section>

      <section className="section" id="how-it-works">
        <div className="container">
          <Reveal className="section__head">
            <p className="section__eyebrow">Как работает</p>
            <h2 className="section__title">От вопроса до ответа — 4 шага</h2>
            <p className="section__desc">
              Строгий конвейер приоритизирует корректность запроса, защиту
              данных и стабильность системы.
            </p>
          </Reveal>
          <div className="steps">
            {STEPS.map((step, i) => (
              <Reveal key={step.num} className="step" delay={i * 90}>
                <span className="step__num">{step.num}</span>
                <div className="step__icon">
                  <step.icon width={26} height={26} />
                </div>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="section section--tinted" id="features">
        <div className="container">
          <Reveal className="section__head">
            <p className="section__eyebrow">Возможности</p>
            <h2 className="section__title">Безопасно, прозрачно, для всех</h2>
            <p className="section__desc">
              Можно начать без входа — гостю доступны общие агрегированные
              данные.
            </p>
          </Reveal>
          <div className="features">
            {FEATURES.map((feature, i) => (
              <Reveal key={feature.title} className="feature" delay={(i % 3) * 90}>
                <div className="feature__icon">
                  <feature.icon width={22} height={22} />
                </div>
                <h3>{feature.title}</h3>
                <p>{feature.text}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="section" id="roles">
        <div className="container">
          <Reveal className="section__head">
            <p className="section__eyebrow">Кто может спросить</p>
            <h2 className="section__title">Каждая роль — свои данные</h2>
            <p className="section__desc">
              Войдите, чтобы получать ответы по своей роли. Без входа доступны
              общие данные абитуриента.
            </p>
          </Reveal>
          <div className="roles">
            {ROLES.map((role, i) => (
              <Reveal key={role.title} className="role-card" delay={(i % 4) * 90}>
                <span className="role-card__tag" style={role.tagStyle}>
                  <role.icon width={14} height={14} />
                </span>
                <h3>{role.title}</h3>
                <ul>
                  {role.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="section section--tinted">
        <div className="container">
          <Reveal className="cta">
            <h2>Готовы спросить?</h2>
            <p>Вход не обязателен — начните как гость.</p>
            <Link to="/chat" className="btn btn-primary btn-lg">
              Открыть чат
              <IconArrowRight width={18} height={18} />
            </Link>
          </Reveal>
        </div>
      </section>

      <SiteFooter />
    </>
  );
}