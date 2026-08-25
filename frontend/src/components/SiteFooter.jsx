import { Link } from "react-router-dom";
import Logo from "./Logo.jsx";

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="container site-footer__inner">
        <Logo />
        <p className="site-footer__note">
          Baikal — безопасный text-to-SQL помощник для данных университета.
          Спросите по-человечески, получите проверенный ответ.
        </p>
        <nav className="site-footer__nav" aria-label="Навигация в футере">
          <Link to="/chat">Чат</Link>
          <Link to="/login">Вход</Link>
        </nav>
      </div>
    </footer>
  );
}