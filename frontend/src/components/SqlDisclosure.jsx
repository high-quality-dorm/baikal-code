import { useState } from "react";
import { IconCode, IconCopy, IconCheck } from "./icons.jsx";

/** Простая подсветка ключевых слов SQL. */
function highlightSql(sql) {
  const tokens = sql.split(/(\s+)/);
  return tokens.map((token, i) => {
    if (/^(SELECT|FROM|WHERE|GROUP BY|ORDER BY|LIMIT|COUNT|AVG|SUM|ROUND|AS)$/i.test(token)) {
      return (
        <span key={i} className="kw">
          {token}
        </span>
      );
    }
    return <span key={i}>{token}</span>;
  });
}

function MetaRow({ meta }) {
  return (
    <div className="sql-block__meta meta-row">
      {meta.row_count !== undefined && <span>{meta.row_count} стр.</span>}
      {meta.duration_ms !== undefined && <span>{Math.round(meta.duration_ms)} ms</span>}
      {meta.truncated && <span>обрезка (лимит 200)</span>}
    </div>
  );
}

export default function SqlDisclosure({ sql, meta }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard недоступен — игнорируем */
    }
  }

  return (
    <div>
      <button
        type="button"
        className="sql-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <IconCode width={15} height={15} />
        {open ? "Скрыть SQL" : "Посмотреть SQL"}
      </button>
      {open && (
        <div className="sql-block">
          <div className="sql-block__head">
            <span>SQL</span>
            <button type="button" className="sql-block__copy" onClick={copy}>
              {copied ? (
                <>
                  <IconCheck width={14} height={14} /> Скопировано
                </>
              ) : (
                <>
                  <IconCopy width={14} height={14} /> Копировать
                </>
              )}
            </button>
          </div>
          <pre className="sql-block__code">{highlightSql(sql)}</pre>
          <MetaRow meta={meta} />
        </div>
      )}
    </div>
  );
}