import { useId } from "react";

type BrandLogoProps = {
  compact?: boolean;
  className?: string;
};

function cx(...values: Array<string | undefined>) {
  return values.filter(Boolean).join(" ");
}

export function BrandLogo({ compact = false, className }: BrandLogoProps) {
  const uid = useId();
  const gradientId = `hermes-brand-gradient-${uid.replace(/:/g, "")}`;

  return (
    <div className={cx("inline-flex items-center gap-3", className)}>
      <svg
        aria-label="Hermes logo"
        fill="none"
        height="32"
        viewBox="0 0 48 48"
        width="32"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient
            id={gradientId}
            x1="0"
            x2="48"
            y1="0"
            y2="48"
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor="#fbbf24" />
            <stop offset="1" stopColor="#f97316" />
          </linearGradient>
        </defs>

        <g transform="skewX(-12) translate(6, 0)">
          <rect x="6" y="6" width="8" height="36" rx="2" fill={`url(#${gradientId})`} />
          <rect x="28" y="6" width="8" height="36" rx="2" fill={`url(#${gradientId})`} />
          <rect x="6" y="20" width="30" height="8" rx="2" fill={`url(#${gradientId})`} />
          <path d="M 36 6 L 46 6 L 36 16 Z" fill={`url(#${gradientId})`} opacity="0.8" />
        </g>
      </svg>

      {compact ? null : (
        <span
          className="text-lg font-semibold tracking-[0.18em] text-white"
          data-brand-text="true"
        >
          Hermes
        </span>
      )}
    </div>
  );
}
