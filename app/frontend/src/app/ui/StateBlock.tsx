import type { ReactNode } from "react";

type StateTone = "loading" | "error" | "empty";

const TONE_CLASSES: Record<StateTone, string> = {
  loading: "border-amber-400/20 bg-amber-400/[0.04] text-slate-200",
  error: "border-rose-400/30 bg-rose-500/[0.08] text-rose-100",
  empty: "border-white/10 bg-white/[0.03] text-slate-300",
};

type StateBlockProps = {
  tone: StateTone;
  title: string;
  description?: string;
  action?: ReactNode;
};

export function StateBlock({ tone, title, description, action }: StateBlockProps) {
  return (
    <div className={`rounded-xl border p-5 ${TONE_CLASSES[tone]}`}>
      <p className="text-sm font-semibold">{title}</p>
      {description ? <p className="mt-2 text-sm leading-6 opacity-90">{description}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
