import { createContext, useContext, useEffect, useState } from "react";
import { fetchUser, login } from "./api.js";

const AuthContext = createContext(null);

const STORAGE_KEY = "baikal-auth";

function loadSession() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function saveSession(session) {
  if (session) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(loadSession);
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    async function hydrate() {
      if (!session) {
        setBooting(false);
        return;
      }
      try {
        const me = await fetchUser(session.accessToken);
        setUser(me);
      } catch {
        // Токен протух или сервер недоступен — сбрасываем сессию.
        setSession(null);
        saveSession(null);
        setUser(null);
      } finally {
        setBooting(false);
      }
    }
    hydrate();
  }, [session]);

  // Синхронизация между окнами/iframe одного origin: вход/выход в другой
  // вкладке подхватывается (нужно для виджета, встроенного через iframe).
  useEffect(() => {
    function onStorage(e) {
      if (e.key !== STORAGE_KEY) return;
      if (e.newValue) {
        try {
          setSession(JSON.parse(e.newValue));
        } catch {
          /* невалидное значение — игнорируем */
        }
      } else {
        setSession(null);
        setUser(null);
      }
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  async function signIn(email, password) {
    const token = await login(email, password);
    const next = { accessToken: token.access_token };
    saveSession(next);
    setSession(next);
    const me = await fetchUser(token.access_token);
    setUser(me);
    return me;
  }

  function signOut() {
    setSession(null);
    saveSession(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider
      value={{ session, user, booting, isAuthed: !!user, signIn, signOut }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}