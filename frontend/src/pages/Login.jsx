import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import Logo from "../components/Logo.jsx";
import ThemeToggle from "../components/ThemeToggle.jsx";
import { useAuth } from "../lib/auth.jsx";
import { ApiError } from "../lib/api.js";
import { IconEye, IconEyeOff, IconShield, IconLock, IconGauge, IconArrowRight } from "../components/icons.jsx";

export default function Login() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from || "/chat";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (submitting) return;
    setError("");
    setSubmitting(true);
    try {
      await signIn(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          err.status === 401
            ? "Неверный email или пароль."
            : err.message || "Не удалось войти. Попробуйте ещё раз."
        );
      } else {
        setError("Не удалось связаться с сервером. Попробуйте ещё раз.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login">
      <aside className="login__panel">
        <Logo />
        <h2>Ваш вопрос, проверенный ответ</h2>
        <p>
          Войдите, чтобы получать ответы по своей роли: студент, преподаватель
          или администрация.
        </p>
        <ul className="login__panel-list">
          <li>
            <IconShield width={18} height={18} />
            Роли и row-level security. Каждый видит только свои данные
          </li>
          <li>
            <IconLock width={18} height={18} />
            Персональные данные студентов маскируются
          </li>
          <li>
            <IconGauge width={18} height={18} />
            Быстрые и безопасные ответы на естественном языке
          </li>
        </ul>
      </aside>

      <main className="login__form-wrap">
        <div className="login__card">
          <div className="login__card-head">
            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
              <ThemeToggle />
            </div>
            <h1>Войти</h1>
            <p>Получайте ответы по своей роли.</p>
          </div>

          {error && (
            <div className="login__error" role="alert">
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <path d="M12 9v4M12 17h.01" />
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              </svg>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate>
            <div className="field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                placeholder="you@university.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="password">Пароль</label>
              <div className="password-wrap">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
                  aria-pressed={showPassword}
                >
                  {showPassword ? (
                    <IconEyeOff width={19} height={19} />
                  ) : (
                    <IconEye width={19} height={19} />
                  )}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary login__submit"
              disabled={submitting || !email.trim() || !password}
            >
              {submitting ? "Входим…" : "Войти"}
              {!submitting && <IconArrowRight width={17} height={17} />}
            </button>
          </form>

          <div className="login__links">
            <Link to="/chat">Продолжить как гость</Link>
            <Link to="/">На главную</Link>
          </div>

          <p className="login__note">
            Вход не обязателен. Без входа доступны общие агрегированные данные
            (направления подготовки, количество мест, статистика приёма).
          </p>
        </div>
      </main>
    </div>
  );
}