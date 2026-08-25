const API_BASE = "/api/v1";

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

export async function ask(question, { token } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/ask`, {
    method: "POST",
    headers,
    body: JSON.stringify({ text: question }),
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
  return res.json();
}

/** /ask ещё не реализован на бэкенде — сигнал переключиться на mock. */
export class EndpointMissingError extends Error {
  constructor() {
    super("endpoint-not-ready");
  }
}