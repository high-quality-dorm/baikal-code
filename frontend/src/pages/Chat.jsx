import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Logo from "../components/Logo.jsx";
import ThemeToggle from "../components/ThemeToggle.jsx";
import RoleBadge from "../components/RoleBadge.jsx";
import SqlDisclosure from "../components/SqlDisclosure.jsx";
import Markdown from "../components/Markdown.jsx";
import { useAuth } from "../lib/auth.jsx";
import { askStream, ApiError, EndpointMissingError } from "../lib/api.js";
import { mockAnswer, SUGGESTED_QUESTIONS } from "../lib/mock.js";
import {
  IconSend,
  IconStop,
  IconX,
  IconAlert,
  IconUser,
  IconSparkles,
} from "../components/icons.jsx";

const MAX_LEN = 2000;

/** Собирает текст запроса: предыдущие реплики беседы + новый вопрос. */
function buildContext(messages, question) {
  const lines = [];
  for (const msg of messages) {
    if (!msg.text) continue;
    const label = msg.role === "user" ? "Пользователь" : "Ассистент";
    lines.push(`${label}: ${msg.text}`);
  }
  if (lines.length === 0) return question;
  return `Ранее в беседе:\n${lines.join("\n")}\nНовый вопрос: ${question}`;
}

function TypingDots() {
  return (
    <span className="typing" aria-label="Ассистент печатает ответ">
      <span />
      <span />
      <span />
    </span>
  );
}

function Message({ message, meta, isLast, status = null, streaming = false }) {
  const isUser = message.role === "user";
  const showStatus = !isUser && streaming && !!status && isLast;
  const showDots = streaming && !message.text && !showStatus;
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
          {showStatus && <div className="msg__status">{status}</div>}
          {meta?.error ? (
            <strong>Не удалось выполнить запрос.</strong>
          ) : isUser ? (
            message.text
          ) : showDots ? (
            <TypingDots />
          ) : (
            <Markdown text={message.text} />
          )}
          {meta?.error && <div style={{ marginTop: 6 }}>{meta.error}</div>}
        </div>
        {!isUser && meta?.sql && isLast && (
          <SqlDisclosure sql={meta.sql} meta={meta} queries={meta.queries} />
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
  const { user, session, isAuthed, signOut } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState(null);
  const [bannerVisible, setBannerVisible] = useState(true);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const pendingRef = useRef(false);
  const abortRef = useRef(null);

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
  }, [messages, pending, status]);

  function stop() {
    abortRef.current?.abort();
  }

  async function send(text) {
    const question = text.trim();
    if (!question || pendingRef.current) return;
    setInput("");
    const assistantId = crypto.randomUUID();
    // Контекст беседы уходит в текст запроса, чтобы LLM знала о предыдущих репликах.
    const payload = buildContext(messages, question);
    setMessages((m) => [
      ...m,
      { id: crypto.randomUUID(), role: "user", text: question },
      { id: assistantId, role: "assistant", text: "", meta: {}, streamed: false },
    ]);
    setPending(true);
    setStatus(null);

    const controller = new AbortController();
    abortRef.current = controller;
    let answerText = "";
    let answerMeta = null;
    let answerQueries = [];
    let streamed = false;
    let finished = false;

    const finish = (textValue, meta, error) => {
      if (finished) return;
      finished = true;
      setPending(false);
      setStatus(null);
      abortRef.current = null;
      const finalMeta = error
        ? { error }
        : {
            ...(meta ?? {}),
            ...(answerQueries.length > 0 ? { queries: answerQueries } : {}),
          };
      setMessages((m) =>
        m.map((msg) =>
          msg.id === assistantId
            ? {
                ...msg,
                text: error ? "" : textValue,
                meta: finalMeta,
                streamed,
              }
            : msg
        )
      );
    };

    try {
      await askStream(payload, {
        token: session?.accessToken,
        signal: controller.signal,
        onStatus: (message) => {
          streamed = true;
          setStatus(message);
        },
        onToken: (delta) => {
          streamed = true;
          answerText += delta;
          // LLM перед вызовом тула может стримить пустые токены ("\n\n") —
          // они не должны давать отступ в начале ответа.
          answerText = answerText.trimStart();
          // Начался текст ответа — статусная строка этапа больше не нужна.
          setStatus(null);
          setMessages((m) =>
            m.map((msg) =>
              msg.id === assistantId ? { ...msg, text: answerText } : msg
            )
          );
        },
        onQuery: (query) => {
          streamed = true;
          answerMeta = {
            sql: query.sql,
            row_count: query.row_count,
            truncated: query.truncated,
            duration_ms: query.duration_ms,
          };
          answerQueries.push(answerMeta);
          // Инструмент execute_query сработал — показываем, что идёт сбор данных.
          setStatus("Собираю данные…");
        },
        onDone: (meta) => finish(answerText, meta, null),
        onError: (message) => finish("", null, message),
      });
      // Стрим закрылся без done/error (обрыв соединения) — финализируем тем,
      // что успели получить: текст + последний выполненный SQL.
      finish(answerText, answerMeta, null);
    } catch (err) {
      if (err?.name === "AbortError") {
        // Пользователь нажал «Остановить» — оставляем накопленный текст.
        finish(answerText, answerMeta, null);
      } else if (err instanceof EndpointMissingError) {
        // /ask недоступен (бэкенд не запущен) — отвечаем локальным mock.
        const answer = mockAnswer(payload);
        finish(answer.text, answer.meta, null);
      } else if (err instanceof ApiError) {
        finish("", null, err.message);
      } else {
        finish("", null, "Не удалось связаться с сервером. Попробуйте ещё раз.");
      }
    }
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
                  {user.email && (
                    <span className="chat__user-name">{user.email}</span>
                  )}
                </>
              ) : (
                <RoleBadge guest />
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
                status={status}
                streaming={pending && i === messages.length - 1}
              />
            ))}
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
              className={`composer__send${pending ? " composer__send--stop" : ""}`}
              onClick={pending ? stop : () => send(input)}
              disabled={!pending && !input.trim()}
              aria-label={pending ? "Остановить ответ" : "Отправить вопрос"}
            >
              {pending ? (
                <IconStop width={20} height={20} />
              ) : (
                <IconSend width={20} height={20} />
              )}
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