const ROLE_LABELS = {
  applicant: "Абитуриент",
  student: "Студент",
  teacher: "Преподаватель",
  admin: "Администрация",
};

export default function RoleBadge({ role }) {
  if (!role) return <span className="badge badge--guest">Гость</span>;
  const label = ROLE_LABELS[role] ?? role;
  return (
    <span className={`badge badge--${role}`} title={`Роль: ${label}`}>
      {label}
    </span>
  );
}