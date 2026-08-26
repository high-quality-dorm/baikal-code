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

const STEPS = [
  {
    icon: IconSparkles,
    title: "Задайте вопрос",
    text: "Напишите своими словами, что хотите узнать. Например: «Сколько бюджетных мест в этом году?»",
  },
  {
    icon: IconDatabase,
    title: "Получите понятный ответ",
    text: "Baikal находит нужные данные и отвечает простым языком — с источником для проверки.",
  },
  {
    icon: IconClipboard,
    title: "Уточняйте, если нужно",
    text: "Продолжайте диалог: сравнивайте, уточняйте и задавайте новые вопросы.",
  },
];

const FEATURES = [
  {
    icon: IconSparkles,
    title: "Вопросы простыми словами",
    text: "Никаких сложных запросов: сформулируйте вопрос как в разговоре — Baikal сам найдёт ответ в данных университета.",
    featured: true,
  },
  {
    icon: IconLock,
    title: "Личные данные защищены",
    text: "Персональные данные студентов недоступны. Ответы обезличенные или агрегированные.",
  },
  {
    icon: IconUsers,
    title: "Каждый видит только своё",
    text: "Студент — свою успеваемость, преподаватель — свои курсы, администрация — сводные данные.",
  },
  {
    icon: IconClipboard,
    title: "Ответ можно проверить",
    text: "Раскройте детали ответа и посмотрите, на чём основан результат.",
  },
  {
    icon: IconGauge,
    title: "Быстрые ответы",
    text: "От вопроса до ответа — секунды, без ожидания отчётов и выгрузок.",
  },
  {
    icon: IconShield,
    title: "Можно начать без входа",
    text: "Гостю открыты общие данные: направления подготовки, места, статистика приёма.",
  },
];

const ROLES = [
  {
    icon: IconBook,
    title: "Абитуриент",
    tone: "applicant",
    items: [
      "Направления подготовки",
      "Бюджетные и платные места",
      "Статистика приёма прошлых лет",
      "Проходные баллы",
    ],
  },
  {
    icon: IconGraduation,
    title: "Студент",
    tone: "student",
    items: [
      "Собственная успеваемость",
      "Средний балл за семестр",
      "Академические задолженности",
      "Расписание занятий",
    ],
  },
  {
    icon: IconUsers,
    title: "Преподаватель",
    tone: "teacher",
    items: [
      "Список своих дисциплин",
      "Средний балл по дисциплине",
      "Процент неаттестованных",
      "Учебная нагрузка",
    ],
  },
  {
    icon: IconBuilding,
    title: "Администрация",
    tone: "admin",
    items: [
      "Численность по факультетам",
      "Статистика приёма",
      "Заполняемость аудиторий",
      "Нагрузка преподавателей",
    ],
  },
];

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
                Ответы о данных университета
              </span>
            </Reveal>
            <Reveal delay={80}>
              <h1 className="hero__title">
                Спросите базу данных <em>по-человечески</em>
              </h1>
            </Reveal>
            <Reveal delay={160}>
              <p className="hero__subtitle">
                Напишите вопрос обычными словами — и получите понятный ответ
                о направлениях, баллах, местах и успеваемости. Личные данные
                защищены.
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
          </div>

          <Reveal delay={200} className="hero-demo">
            <div className="hero-demo__card">
              <div className="hero-demo__body">
                <div className="hero-demo__question">
                  Сколько студентов обучается в университете?
                </div>
                <div className="hero-demo__answer">
                  В университете обучается <strong>500</strong> студентов на{" "}
                  <strong>26</strong> направлениях подготовки.
                </div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="section" id="how-it-works">
        <div className="container">
          <Reveal className="section__head">
            <h2 className="section__title">Как это работает</h2>
            <p className="section__desc">
              Три простых шага — и вы получите нужный ответ.
            </p>
          </Reveal>
          <ol className="steps">
            {STEPS.map((step, i) => (
              <Reveal as="li" key={step.title} className="step" delay={i * 90}>
                <div className="step__icon">
                  <step.icon width={24} height={24} />
                </div>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                </div>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      <section className="section section--tinted" id="features">
        <div className="container">
          <Reveal className="section__head">
            <h2 className="section__title">Возможности</h2>
            <p className="section__desc">
              Всё нужное, чтобы быстро получать ответы о данных университета.
            </p>
          </Reveal>
          <div className="features">
            {FEATURES.map((feature, i) => (
              <Reveal
                key={feature.title}
                className={`feature${feature.featured ? " feature--wide" : ""}`}
                delay={(i % 2) * 90}
              >
                <div className="feature__icon">
                  <feature.icon width={22} height={22} />
                </div>
                <div>
                  <h3>{feature.title}</h3>
                  <p>{feature.text}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="section" id="roles">
        <div className="container">
          <Reveal className="section__head">
            <h2 className="section__title">Каждая роль видит свои данные</h2>
            <p className="section__desc">
              Войдите, чтобы получать ответы по своей роли. Без входа доступны
              общие данные.
            </p>
          </Reveal>
          <div className="roles">
            {ROLES.map((role, i) => (
              <Reveal key={role.title} className="role-card" delay={(i % 4) * 90}>
                <div className={`role-card__tag role-card__tag--${role.tone}`}>
                  <role.icon width={15} height={15} />
                </div>
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
            <p>Вход не обязателен. Начните как гость.</p>
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