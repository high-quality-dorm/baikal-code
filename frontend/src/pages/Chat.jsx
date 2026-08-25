import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Logo from "../components/Logo.jsx";
import ThemeToggle from "../components/ThemeToggle.jsx";
import RoleBadge from "../components/RoleBadge.jsx";
import SqlDisclosure from "../components/SqlDisclosure.jsx";
import { useAuth } from "../lib/auth.jsx";
import { useTypewriter } from "../lib/typewriter.js";
import { ask, ApiError, EndpointMissingError } from "../lib/api.js";
import { mockAnswer, SUGGESTED_QUESTIONS } from "../lib/mock.js";
import {
  IconSend,
  IconX,
  IconAlert,
  IconUser,
  IconSparkles,
} from "../components/icons.jsx";

const MAX_LEN = 2000;

function TypingDots() {
  return (
    <span className="typing" aria-label="Ассистент печатает ответ">
      <span />
      <span />
      <span />
    </span>
  );
}

function AssistantText({ text }) {
  const visible = useTypewriter(text);
  const done = visible >= text.length;
  return (
    <>
      {text.slice(0, visible)}
      {!done && <span className="stream-caret" aria-hidden="true" />}
    </>
  );
}

function Message({ message, meta, isLast }) {
  const isUser = message.role === "user";
  return (
    <article className={`msg msg--${message.role}${meta?.error ? " msg--error" : ""}`}>
      <div className="msg__avatar" aria-hidden="true">
        {isUser ? (
          <IconUser width={18} height={18} />
        ) : (
          <IconSparkles width={18} height={18} />
        )}
      </div>
      <div className="msg__body">
        <div className="msg__bubble">
          {meta?.error ? (
            <strong>Не удалось выполнить запрос.</strong>
          ) : isUser ? (
            message.text
          ) : (
            <AssistantText text={message.text} />
          )}
          {meta?.error && <div style={{ marginTop: 6 }}>{meta.error}</div>}
        </div>
        {!isUser && meta?.sql && isLast && (
          <SqlDisclosure sql={meta.sql} meta={meta} />
        )}
        {!isUser && meta?.row_count !== undefined && !meta?.error && (
          <div className="msg__meta">
            <span>{meta.row_count} стр.</span>
            <span>{meta.duration_ms} ms</span>
            {meta.truncated && <span>обрезка</span>}
          </div>
        )}
      </div>
    </article>
  );
}

export default function Chat() {
  const { user, isAuthed, signOut } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [bannerVisible, setBannerVisible] = useState(true);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const pendingRef = useRef(false);

  useEffect(() => {
    pendingRef.current = pending;
  }, [pending]);

  // Помечаем страницу для стилизации скроллбара чата (убираем при уходе).
  useEffect(() => {
    document.body.classList.add("chat-page");
    return () => document.body.classList.remove("chat-page");
  }, []);

  // Автопрокрутка к последнему сообщению.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, pending]);

  async function send(text) {
    const question = text.trim();
    if (!question || pendingRef.current) return;
    setInput("");
    setPending(true);
    setMessages((m) => [
      ...m,
      { id: crypto.randomUUID(), role: "user", text: question },
    ]);

    const headers = { "Content-Type": "application/json" };
    if (user?.role) headers["X-Role"] = user.role;
    if (user?.internal_id) headers["X-User-Id"] = String(user.internal_id);

    let answer;
    try {
      answer = await ask(question, {
        role: user?.role,
        user_id: user?.internal_id,
      });
    } catch (err) {
      if (err instanceof EndpointMissingError) {
        // /ask ещё не реализован на бэкенде — отвечаем локальным mock.
        answer = mockAnswer(question);
      } else if (err instanceof ApiError) {
        setMessages((m) => [
          ...m,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            text: "",
            meta: { error: err.message },
          },
        ]);
        setPending(false);
        return;
      } else {
        setMessages((m) => [
          ...m,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            text: "",
            meta: {
              error: "Не удалось связаться с сервером. Попробуйте ещё раз.",
            },
          },
        ]);
        setPending(false);
        return;
      }
    }

    setMessages((m) => [
      ...m,
      {
        id: crypto.randomUUID(),
        role: "assistant",
        text: answer.text,
        meta: answer.meta,
      },
    ]);
    setPending(false);
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (pending) {
        // Enter во время ответа не должен отправлять повторно.
        return;
      }
      send(input);
    }
  }

  const nearLimit = input.length > MAX_LEN - 100;

  const suggested = useMemo(
    () =>
      user?.role
        ? SUGGESTED_QUESTIONS
        : SUGGESTED_QUESTIONS.slice(0, 2).concat([
            "Какие бюджетные места есть в этом году?",
          ]),
    [user?.role]
  );

  const isEmpty = messages.length === 0;

  return (
    <div className="chat">
      <header className="chat__header">
        <div className="chat__header-inner">
          <div className="chat__header-left">
            <Logo />
            <div className="chat__header-user">
              {isAuthed ? (
                <>
                  <RoleBadge role={user.role} />
                  {user.display_name && (
                    <span className="chat__user-name">{user.display_name}</span>
                  )}
                </>
              ) : (
                <RoleBadge role={null} />
              )}
            </div>
          </div>
          <div className="chat__header-actions">
            <ThemeToggle />
            {isAuthed ? (
              <button type="button" className="btn btn-ghost" onClick={signOut}>
                Выйти
              </button>
            ) : (
              <Link to="/login" className="btn btn-primary">
                Войти
              </Link>
            )}
          </div>
        </div>
      </header>

      {!isAuthed && bannerVisible && (
        <div className="guest-banner">
          <div className="guest-banner__inner">
            <div className="guest-banner__text">
              <IconAlert width={18} height={18} />
              <span>
                Вы вошли как гость. Доступны только общие агрегированные
                данные.{" "}
                <Link to="/login" style={{ fontWeight: 600 }}>
                  Войдите
                </Link>
                , чтобы получать ответы по своей роли.
              </span>
            </div>
            <div className="guest-banner__actions">
              <button
                type="button"
                className="guest-banner__close"
                onClick={() => setBannerVisible(false)}
                aria-label="Скрыть подсказку"
              >
                <IconX width={16} height={16} />
              </button>
            </div>
          </div>
        </div>
      )}

      <main className="chat__messages" aria-live="polite">
        {isEmpty && !pending ? (
          <div className="chat__empty">
            <div className="chat__empty-mark">
              <IconSparkles width={32} height={32} />
            </div>
            <h1 className="chat__empty-title">
              Спросите что угодно о данных университета
            </h1>
            <p className="chat__empty-sub">
              Опишите, что хотите узнать. Baikal построит проверенный SQL и
              вернёт понятный ответ.
            </p>
            <div className="chat__empty-suggest">
              {suggested.map((q) => (
                <button
                  key={q}
                  type="button"
                  className="chip"
                  onClick={() => send(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((message, i) => (
              <Message
                key={message.id}
                message={message}
                meta={message.meta}
                isLast={i === messages.length - 1}
              />
            ))}
            {pending && (
              <article className="msg msg--assistant">
                <div className="msg__avatar" aria-hidden="true">
                  <IconSparkles width={18} height={18} />
                </div>
                <div className="msg__body">
                  <div className="msg__bubble">
                    <TypingDots />
                  </div>
                </div>
              </article>
            )}
            <div ref={scrollRef} className="chat__scroll-anchor" />
          </>
        )}
      </main>

      <div className="chat__composer">
        <div className="chat__composer-inner">
          <div className="composer">
            <textarea
              ref={inputRef}
              className="composer__input"
              rows={1}
              placeholder="Задайте вопрос о данных университета…"
              value={input}
              maxLength={MAX_LEN}
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = Math.min(e.target.scrollHeight, 180) + "px";
              }}
              onKeyDown={handleKeyDown}
              aria-label="Текст вопроса"
            />
            <button
              type="button"
              className="composer__send"
              onClick={() => send(input)}
              disabled={!input.trim() || pending}
              aria-label="Отправить вопрос"
            >
              <IconSend width={20} height={20} />
            </button>
          </div>
          <div className="composer__footer">
            <span className="composer__hint">
              <IconSparkles width={14} height={14} />
              Enter отправить, Shift+Enter новая строка
            </span>
            {nearLimit && (
              <span className="composer__counter">
                {input.length}/{MAX_LEN}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}