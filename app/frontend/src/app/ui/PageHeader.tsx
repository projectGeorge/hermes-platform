import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  description?: string;
  eyebrow?: string;
  actions?: ReactNode;
};

export function PageHeader({ title, description, eyebrow, actions }: PageHeaderProps) {
  return (
    <header className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div className="space-y-2">
        {eyebrow ? (
          <p className="text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
            {eyebrow}
          </p>
        ) : null}
        <div className="space-y-1">
          <h1 className="text-lg font-semibold tracking-tight text-white">{title}</h1>
          {description ? (
            <p className="max-w-3xl text-sm leading-5 text-[var(--hermes-muted)]">
              {description}
            </p>
          ) : null}
        </div>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
