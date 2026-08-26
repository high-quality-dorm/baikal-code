import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Безопасный рендер markdown: raw HTML по умолчанию игнорируется (нет rehype-raw). */
export default function Markdown({ text }) {
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text || ""}</ReactMarkdown>
    </div>
  );
}