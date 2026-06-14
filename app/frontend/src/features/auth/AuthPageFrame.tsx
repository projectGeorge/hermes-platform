import type { ReactNode } from "react";

import { BrandLogo } from "../../app/ui/BrandLogo";

type AuthPageFrameProps = {
  tagline: string;
  children: ReactNode;
};

const featureCallouts = [
  {
    title: "Instant intake",
    desc: "AI extracts freight requests into reviewable structured fields automatically.",
    icon: (
      <svg
        className="h-4 w-4"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        viewBox="0 0 24 24"
      >
        <path
          d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
  {
    title: "Carrier decision surface",
    desc: "Compare scored candidates with route data in one structured view.",
    icon: (
      <svg
        className="h-4 w-4"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        viewBox="0 0 24 24"
      >
        <path
          d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
  {
    title: "Full workflow visibility",
    desc: "One activity feed from inbound request to post-booking confirmation.",
    icon: (
      <svg
        className="h-4 w-4"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        viewBox="0 0 24 24"
      >
        <path
          d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
];

export function AuthPageFrame({ tagline, children }: AuthPageFrameProps) {
  return (
    <main className="flex min-h-screen bg-[var(--hermes-bg)] px-5 py-6 text-white md:px-8">
      <section className="mx-auto grid min-h-[calc(100vh-3rem)] w-full max-w-7xl overflow-hidden rounded-2xl border border-white/[0.08] bg-[var(--hermes-panel)] lg:grid-cols-[0.9fr_1.1fr]">
        {/* Form side */}
        <div className="flex flex-col px-6 py-10 lg:border-r lg:border-[var(--hermes-border)] lg:px-10 xl:px-14">
          {/* Brand anchor — visible on mobile; provides identity before brand side */}
          <div className="mb-8 lg:hidden">
            <BrandLogo />
          </div>
          <div className="flex flex-1 items-center justify-center">
            <div className="w-full max-w-sm">
              {children}
            </div>
          </div>
        </div>

        {/* Brand side — desktop only */}
        <aside className="relative hidden lg:flex lg:flex-col overflow-hidden px-6 py-10 lg:px-10 xl:px-14">
          {/* Amber ambient glow */}
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(245,158,11,0.07),transparent_38%)]" />

          {/* Logo row — top anchor */}
          <div className="relative z-10 flex items-center justify-between gap-4">
            <BrandLogo className="scale-110" />
            <span className="rounded-lg border border-[var(--hermes-accent)]/20 bg-[var(--hermes-accent-soft)] px-3 py-2 text-[0.68rem] font-semibold uppercase tracking-[0.2em] text-[var(--hermes-accent)]">
              Operator access
            </span>
          </div>

          {/* Centered content: headline + cards as one group */}
          <div className="relative z-10 flex flex-1 flex-col justify-center gap-10">
            <div className="space-y-4">
              <p className="text-sm uppercase tracking-[0.24em] text-[var(--hermes-accent)]">
                Hermes workspace
              </p>
              <h1
                className="max-w-lg text-4xl font-bold tracking-tight text-white md:text-5xl"
                style={{ fontFamily: "'Instrument Sans', sans-serif" }}
              >
                Enter the freight workflow with one controlled operator surface.
              </h1>
              <p className="max-w-xl text-base leading-7 text-slate-300">{tagline}</p>
            </div>

            <div className="space-y-3">
              {featureCallouts.map((item) => (
                <div
                  key={item.title}
                  className="flex items-start gap-4 rounded-xl border border-[var(--hermes-border)] bg-[var(--hermes-panel-muted)] px-5 py-4"
                >
                  <span className="mt-0.5 shrink-0 text-[var(--hermes-accent)]">{item.icon}</span>
                  <div>
                    <p className="text-base font-semibold text-[var(--hermes-text)]">{item.title}</p>
                    <p className="mt-1 text-sm leading-5 text-[var(--hermes-muted)]">{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}
