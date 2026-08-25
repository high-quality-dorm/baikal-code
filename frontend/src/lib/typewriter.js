import { useEffect, useRef, useState } from "react";

/** Имитация стриминга: постепенно "печатает" текст.
 *  Уважает prefers-reduced-motion — тогда рендерит сразу весь текст. */
export function useTypewriter(text, speed = 22) {
  const [visible, setVisible] = useState(0);
  const reduce = useRef(false);

  useEffect(() => {
    reduce.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }, []);

  useEffect(() => {
    if (!text) {
      setVisible(0);
      return;
    }
    if (reduce.current) {
      setVisible(text.length);
      return;
    }
    setVisible(0);
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      setVisible(i);
      if (i >= text.length) clearInterval(id);
    }, speed);
    return () => clearInterval(id);
  }, [text, speed]);

  return visible;
}