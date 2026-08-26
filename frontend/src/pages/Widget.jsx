import { useEffect, useRef, useState } from "react";
import Markdown from "../components/Markdown.jsx";
import SqlDisclosure from "../components/SqlDisclosure.jsx";
import RoleBadge from "../components/RoleBadge.jsx";
import { useAuth } from "../lib/auth.jsx";
import { askStream, ApiError, EndpointMissingError } from "../lib/api.js";
import { mockAnswer, SUGGESTED_QUESTIONS } from "../lib/mock.js";
import { buildContext } from "../lib/chatUtils.js";
import {
  IconChat,
  IconSend,
  IconStop,
  IconX,
  IconSparkles,
} from "../components/icons.jsx";

export default function Widget() {
  const { user, session, isAuthed, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState(null);
  const abortRef = useRef(null);
  const scrollRef = useRef(null);
  const pendingRef = useRef(false);

  useEffect(() => {
    pendingRef.current = pending;
  }, [pending]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, pending, status]);

  function openLogin() {
    // Вход в новой вкладке; сессия подхватывается через storage-событие.
    window.open("/login", "_blank", "noopener");
  }

  function stop() {
    abortRef.current?.abort();
  }

  async function send(text) {
    const question = text.trim();
    if (!question || pendingRef.current) return;
    setInput("");
    const assistantId = crypto.randomUUID();
    const payload = buildContext(messages, question);
    setMessages((m) => [
      ...m,
      { id: crypto.randomUUID(), role: "user", text: question },
      { id: assistantId, role: "assistant", text: "", meta: {} },
    ]);
    setPending(true);
    setStatus(null);

    const controller = new AbortController();
    abortRef.current = controller;
    let answerText = "";
    let answerMeta = null;

    const finish = (textValue, meta, error) => {
      setPending(false);
      setStatus(null);
      abortRef.current = null;
      const finalMeta = error ? { error } : { ...(meta ?? {}) };
      setMessages((m) =>
        m.map((msg) =>
          msg.id === assistantId
            ? { ...msg, text: error ? "" : textValue, meta: finalMeta }
            : msg
        )
      );
    };

    try {
      await askStream(payload, {
        token: session?.accessToken,
        signal: controller.signal,
        onStatus: (message) => setStatus(message),
        onToken: (delta) => {
          answerText += delta;
          answerText = answerText.trimStart();
          setStatus(null);
          setMessages((m) =>
            m.map((msg) =>
              msg.id === assistantId ? { ...msg, text: answerText } : msg
            )
          );
        },
        onQuery: (query) => {
          answerMeta = {
            sql: query.sql,
            row_count: query.row_count,
            truncated: query.truncated,
            duration_ms: query.duration_ms,
          };
          setStatus("Собираю данные…");
        },
        onDone: (meta) => finish(answerText, meta, null),
        onError: (message) => finish("", null, message),
      });
      finish(answerText, answerMeta, null);
    } catch (err) {
      if (err?.name === "AbortError") {
        finish(answerText, answerMeta, null);
      } else if (err instanceof EndpointMissingError) {
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
      if (pending) return;
      send(input);
    }
  }

  const suggested = SUGGESTED_QUESTIONS.slice(0, 2);

  return (
    <div className="widget">
      <button
        type="button"
        className="widget__launcher"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Закрыть чат" : "Открыть чат"}
        aria-expanded={open}
      >
        {open ? (
          <IconX width={26} height={26} />
        ) : (
          <IconChat width={26} height={26} />
        )}
      </button>

      {open && (
        <section className="widget__panel">
          <header className="widget__header">
            <span className="widget__header-title">
              <IconSparkles width={16} height={16} />
              Baikal
            </span>
            <div className="widget__header-actions">
              <RoleBadge role={user?.role} guest={!isAuthed} />
              {isAuthed ? (
                <button type="button" className="widget__link" onClick={signOut}>
                  Выйти
                </button>
              ) : (
                <button type="button" className="widget__link" onClick={openLogin}>
                  Войти
                </button>
              )}
            </div>
          </header>

          <div className="widget__messages">
            {messages.length === 0 && !pending ? (
              <div className="widget__empty">
                <p>
                  Спросите о данных университета. Без входа доступны общие
                  агрегированные данные.
                </p>
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
            ) : (
              messages.map((m, i) => {
                const isLast = i === messages.length - 1;
                const streaming = pending && isLast;
                const isUser = m.role === "user";
                return (
                  <div
                    key={m.id}
                    className={`widget__msg widget__msg--${m.role}${
                      m.meta?.error ? " widget__msg--error" : ""
                    }`}
                  >
                    <div className="widget__msg-body">
                      <div className="widget__msg-bubble">
                        {m.meta?.error ? (
                          <strong>Не удалось выполнить запрос.</strong>
                        ) : isUser ? (
                          m.text
                        ) : m.text ? (
                          <Markdown text={m.text} />
                        ) : streaming ? (
                          <span className="typing">
                            <span />
                            <span />
                            <span />
                          </span>
                        ) : null}
                        {m.meta?.error && (
                          <div style={{ marginTop: 6 }}>{m.meta.error}</div>
                        )}
                      </div>
                      {!isUser && m.meta?.sql && (
                        <div style={{ display: "grid", gap: 6 }}>
                          <SqlDisclosure sql={m.meta.sql} meta={m.meta} />
                          {m.meta?.row_count !== undefined && !m.meta?.error && (
                            <div className="widget__msg-meta">
                              <span>{m.meta.row_count} стр.</span>
                              <span>{m.meta.duration_ms} ms</span>
                              {m.meta.truncated && <span>обрезка</span>}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            )}
            <div ref={scrollRef} className="widget__scroll-anchor" />
          </div>

          <div className="widget__composer">
            <textarea
              rows={1}
              placeholder="Задайте вопрос…"
              aria-label="Текст вопроса"
              value={input}
              maxLength={2000}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
            />
            <button
              type="button"
              onClick={pending ? stop : () => send(input)}
              disabled={!pending && !input.trim()}
              aria-label={pending ? "Остановить ответ" : "Отправить вопрос"}
            >
              {pending ? (
                <IconStop width={18} height={18} />
              ) : (
                <IconSend width={18} height={18} />
              )}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}