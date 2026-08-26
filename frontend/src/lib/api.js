// Абсолютный базис из собственного origin: в iframe (виджет /widget) на внешнем
// сайте относительный /api ушёл бы на внешний хост, а не на наш бэкенд.
const API_BASE = `${window.location.origin}/api/v1`;

async function request(path, { method = "GET", body, token } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail ?? detail;
    } catch {
      /* тело не JSON — оставляем statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : "Ошибка сервера");
    this.status = status;
  }
}

export function login(email, password) {
  return request("/auth/login", { method: "POST", body: { email, password } });
}

export function fetchUser(token) {
  return request("/auth/users/me", { token });
}

export async function askStream(
  question,
  { token, signal, onStatus, onToken, onQuery, onDone, onError } = {}
) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/ask`, {
    method: "POST",
    headers,
    body: JSON.stringify({ text: question }),
    signal,
  });
  if (res.status === 404) throw new EndpointMissingError();
  if (!res.ok) {
    // Пытаемся распарсить тело. Если JSON с detail нет — значит ответ пришёл
    // от прокси (бэкенд недоступен), а не от самого API: используем mock.
    let detail;
    try {
      const data = await res.json();
      detail = data?.detail;
    } catch {
      /* тело не JSON */
    }
    if (!detail) throw new EndpointMissingError();
    throw new ApiError(res.status, detail);
  }
  if (!res.body) throw new EndpointMissingError();

  // Ответ — NDJSON-поток от тул-агента (см. ADR 36): status/query/token/done/error.
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newlineIndex;
      while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, newlineIndex).trim();
        buffer = buffer.slice(newlineIndex + 1);
        if (!line) continue;
        let event;
        try {
          event = JSON.parse(line);
        } catch {
          continue;
        }
        switch (event?.type) {
          case "status":
            onStatus?.(event.message);
            break;
          case "token":
            onToken?.(event.text);
            break;
          case "query":
            onQuery?.(event);
            break;
          case "done":
            onDone?.(event.meta);
            break;
          case "error":
            onError?.(event.message);
            break;
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}

/** /ask ещё не реализован на бэкенде — сигнал переключиться на mock. */
export class EndpointMissingError extends Error {
  constructor() {
    super("endpoint-not-ready");
  }
}