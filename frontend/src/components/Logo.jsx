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
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M12 2.5c3.8 4.3 6.3 7.2 6.3 10.2a6.3 6.3 0 0 1-12.6 0c0-3 2.5-5.9 6.3-10.2z" />
          <path d="M6.8 13.4c1.5-1.1 3-1.1 4.4 0 1.5 1.1 3 1.1 4.4 0" opacity="0.8" />
        </svg>
      </span>
      <span className="logo__name">Baikal</span>
    </Link>
  );
}