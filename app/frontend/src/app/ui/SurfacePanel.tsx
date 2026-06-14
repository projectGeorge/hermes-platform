import type { HTMLAttributes, ReactNode } from "react";

type SurfacePanelProps = {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
} & HTMLAttributes<HTMLElement>;

function mergeClasses(...values: Array<string | undefined>) {
  return values.filter(Boolean).join(" ");
}

export function SurfacePanel({
  children,
  className,
  as = "section",
  ...rest
}: SurfacePanelProps) {
  const Tag = as;

  return (
    <Tag
      className={mergeClasses(
        "rounded-xl border border-[var(--hermes-border)] bg-[var(--hermes-panel)] p-5",
        className,
      )}
      {...rest}
    >
      {children}
    </Tag>
  );
}
