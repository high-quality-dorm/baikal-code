import { useState } from "react";
import { IconCode, IconCopy, IconCheck } from "./icons.jsx";

// Ключевые слова для подсветки (одиночные токены, т.к. SQL делится по пробелам).
const KEYWORDS =
  /^(SELECT|FROM|WHERE|GROUP|ORDER|HAVING|LIMIT|JOIN|INNER|LEFT|RIGHT|FULL|ON|UNION|INTERSECT|EXCEPT|AND|OR|NOT|IN|BETWEEN|LIKE|IS|NULL|AS|CASE|WHEN|THEN|ELSE|END|DISTINCT|COUNT|AVG|SUM|ROUND|MIN|MAX)$/i;
// Клаузы, перед которыми делаем смысловой перенос строки.
const CLAUSE_BREAK =
  /^(SELECT|FROM|WHERE|GROUP|ORDER|HAVING|LIMIT|JOIN|INNER|LEFT|RIGHT|FULL|UNION|INTERSECT|EXCEPT|AND|OR|ON)$/i;

/** Подсветка ключевых слов SQL + перенос строк перед смысловыми клаузами. */
function highlightSql(sql) {
  const tokens = sql.split(/(\s+)/);
  const nodes = [];
  let first = true;
  tokens.forEach((token, i) => {
    if (/^\s+$/.test(token)) {
      nodes.push(<span key={i}>{token}</span>);
      return;
    }
    if (CLAUSE_BREAK.test(token) && !first) {
      nodes.push(<br key={`br-${i}`} />);
    }
    nodes.push(
      <span key={`t-${i}`} className={KEYWORDS.test(token) ? "kw" : undefined}>
        {token}
      </span>
    );
    first = false;
  });
  return nodes;
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

export default function SqlDisclosure({ sql, meta, queries }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const list =
    queries && queries.length > 0
      ? queries.map((q) => ({ sql: q.sql, meta: q }))
      : [{ sql, meta }];

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
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
        <div className="sql-blocks">
          {list.map((item, i) => (
            <div className="sql-block" key={i}>
              <div className="sql-block__head">
                <span>{list.length > 1 ? `SQL ${i + 1}` : "SQL"}</span>
                <button
                  type="button"
                  className="sql-block__copy"
                  onClick={() => copy(item.sql)}
                >
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
              <pre className="sql-block__code">{highlightSql(item.sql)}</pre>
              <MetaRow meta={item.meta} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}