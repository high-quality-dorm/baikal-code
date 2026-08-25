import { Link, useNavigate } from "react-router-dom";
import Logo from "./Logo.jsx";
import ThemeToggle from "./ThemeToggle.jsx";
import { useAuth } from "../lib/auth.jsx";
import RoleBadge from "./RoleBadge.jsx";

export default function SiteHeader() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  return (
    <header className="site-header">
      <div className="container site-header__inner">
        <Logo />
        <nav className="site-header__nav" aria-label="Основная навигация">
          <a className="site-header__link" href="/#features">
            Возможности
          </a>
          <a className="site-header__link" href="/#how-it-works">
            Как работает
          </a>
          <a className="site-header__link" href="/#roles">
            Роли
          </a>
        </nav>
        <div className="site-header__actions">
          <ThemeToggle />
          {user ? (
            <>
              <RoleBadge role={user.role} />
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => {
                  signOut();
                  navigate("/");
                }}
              >
                Выйти
              </button>
            </>
          ) : (
            <>
              <Link className="btn btn-ghost" to="/login">
                Войти
              </Link>
              <Link className="btn btn-primary" to="/chat">
                <span className="header-chat-label">Открыть чат</span>
                <svg
                  className="header-chat-icon"
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  aria-hidden="true"
                >
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}