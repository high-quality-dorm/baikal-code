/** Собирает текст запроса: предыдущие реплики беседы + новый вопрос. */
export function buildContext(messages, question) {
  const lines = [];
  for (const msg of messages) {
    if (!msg.text) continue;
    const label = msg.role === "user" ? "Пользователь" : "Ассистент";
    lines.push(`${label}: ${msg.text}`);
  }
  if (lines.length === 0) return question;
  return `Ранее в беседе:\n${lines.join("\n")}\nНовый вопрос: ${question}`;
}