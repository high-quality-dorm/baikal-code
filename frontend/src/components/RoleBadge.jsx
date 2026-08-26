const ROLE_LABELS = {
  applicant: "Абитуриент",
  student: "Студент",
  teacher: "Преподаватель",
  head: "Заведующий",
  dean: "Декан",
  admin: "Администрация",
};

export default function RoleBadge({ role, guest = false }) {
  if (guest) return <span className="badge badge--guest">Гость</span>;
  if (!role) return <span className="badge">Пользователь</span>;
  const label = ROLE_LABELS[role] ?? role;
  return (
    <span className={`badge badge--${role}`} title={`Роль: ${label}`}>
      {label}
    </span>
  );
}