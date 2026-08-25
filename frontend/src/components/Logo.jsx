import { Link } from "react-router-dom";

export default function Logo({ size = "md" }) {
  return (
    <Link to="/" className="logo" aria-label="Baikal, на главную">
      <span className="logo__mark">
        <svg
          width={size === "lg" ? 26 : 22}
          height={size === "lg" ? 26 : 22}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          aria-hidden="true"
        >
          <path d="M3 9c3.5-3.5 7.5-3.5 11 0s7.5 3.5 11 0" />
          <path d="M3 15c3.5-3.5 7.5-3.5 11 0s7.5 3.5 11 0" opacity="0.55" />
        </svg>
      </span>
      <span className="logo__name">Baikal</span>
    </Link>
  );
}