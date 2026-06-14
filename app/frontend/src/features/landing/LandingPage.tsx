import { useAuth } from "@clerk/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { BrandLogo } from "../../app/ui/BrandLogo";

// ─── Reveal on scroll ─────────────────────────────────────────
function Reveal({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setVisible(true); },
      { threshold: 0.06, rootMargin: "0px 0px -40px 0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className="h-full transition-all duration-600 ease-out"
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(28px)",
        transitionDelay: visible ? `${delay}ms` : "0ms",
        willChange: "transform, opacity",
      }}
    >
      {children}
    </div>
  );
}

// ─── Feature preview components ───────────────────────────────

function IntakePreview() {
  const fields = [
    { label: "Origin", value: "Madrid, ES", ok: true },
    { label: "Destination", value: "Paris, FR", ok: true },
    { label: "Cargo type", value: "General freight", ok: true },
    { label: "Weight (kg)", value: "Needs review", ok: false },
  ];
  return (
    <div className="h-full rounded-lg border border-[var(--hermes-border)] bg-[var(--hermes-panel)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[0.62rem] font-medium uppercase tracking-[0.22em] text-[var(--hermes-muted)]">
          Intake review
        </p>
        <span className="rounded-md border border-[var(--hermes-accent)]/20 bg-[var(--hermes-accent-soft)] px-2 py-0.5 text-[0.6rem] text-[var(--hermes-accent)]">
          7 fields
        </span>
      </div>
      <div className="space-y-1.5">
        {fields.map((f) => (
          <div
            key={f.label}
            className="flex items-center justify-between rounded bg-[var(--hermes-panel-strong)] px-2.5 py-1.5"
          >
            <span className="text-[0.62rem] text-[var(--hermes-muted)]">{f.label}</span>
            <div className="flex items-center gap-1.5">
              <span className="text-[0.62rem] text-[var(--hermes-text)]">{f.value}</span>
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: f.ok ? "#34d399" : "#fb923c" }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CarrierMatchPreview() {
  const candidates = [
    { name: "MaritimaCargo", route: "MAD → CDG", score: 94, selected: true },
    { name: "TransEurope SL", route: "MAD → CDG", score: 81, selected: false },
    { name: "SpeedFreight", route: "MAD → CDG", score: 73, selected: false },
  ];
  return (
    <div className="h-full rounded-lg border border-[var(--hermes-border)] bg-[var(--hermes-panel)] p-4">
      <p className="mb-3 text-[0.62rem] font-medium uppercase tracking-[0.22em] text-[var(--hermes-muted)]">
        Carrier candidates
      </p>
      <div className="space-y-2">
        {candidates.map((c) => (
          <div
            key={c.name}
            className={`flex items-center justify-between rounded-lg border px-3 py-2 ${
              c.selected
                ? "border-amber-400/30 bg-amber-400/[0.05]"
                : "border-[var(--hermes-border)] bg-[var(--hermes-panel-strong)]"
            }`}
          >
            <div className="min-w-0">
              <p className="text-[0.66rem] font-medium text-[var(--hermes-text)]">{c.name}</p>
              <p className="text-[0.58rem] text-[var(--hermes-muted)]">{c.route}</p>
            </div>
            <span className="shrink-0 rounded-md border border-[#60a5fa]/25 bg-[rgba(96,165,250,0.10)] px-1.5 py-0.5 text-[0.6rem] font-semibold text-[#60a5fa]">
              {c.score}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SmartCommsPreview() {
  const messages = [
    { role: "user" as const, text: "What's the status of ORD-0041?" },
    { role: "assistant" as const, text: "ORD-0041 (Acme Logistics, MAD → CDG) is confirmed. Carrier: MaritimaCargo. Pickup scheduled Jun 12, ETA Jun 14." },
    { role: "user" as const, text: "Any alerts on this shipment?" },
    { role: "assistant" as const, text: "No active alerts. Margin is 18%, above the 10% risk threshold. All documents valid." },
  ];
  return (
    <div className="h-full rounded-lg border border-[var(--hermes-border)] bg-[var(--hermes-panel)] p-4">
      <p className="mb-3 text-[0.62rem] font-medium uppercase tracking-[0.22em] text-[var(--hermes-muted)]">
        Smart Comms
      </p>
      <div className="space-y-2.5">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-lg px-2.5 py-1.5 text-[0.6rem] leading-[1.45] ${
                m.role === "user"
                  ? "rounded-br-sm bg-[var(--hermes-accent)]/15 text-[var(--hermes-accent)]"
                  : "rounded-bl-sm bg-[var(--hermes-panel-strong)] text-[var(--hermes-text)]"
              }`}
            >
              {m.text}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-1.5 rounded-md border border-[var(--hermes-border)] bg-[var(--hermes-panel-strong)] px-2.5 py-1.5">
        <span className="text-[0.58rem] text-[var(--hermes-muted)]">Ask about orders, carriers…</span>
      </div>
    </div>
  );
}

function TrackingPreview() {
  return (
    <div className="h-full rounded-lg border border-[var(--hermes-border)] bg-[var(--hermes-panel)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[0.62rem] font-medium uppercase tracking-[0.22em] text-[var(--hermes-muted)]">
          Shipment tracking
        </p>
        <span className="text-[0.62rem] font-medium text-[var(--hermes-indigo)]">In transit</span>
      </div>
      <div className="mb-3">
        <div className="mb-1.5 flex justify-between text-[0.6rem] text-[var(--hermes-muted)]">
          <span>Rotterdam, NL</span>
          <span>Milan, IT</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-[var(--hermes-panel-strong)]">
          <div
            className="h-full rounded-full"
            style={{ width: "62%", background: "linear-gradient(90deg, #818cf8, #6366f1)" }}
          />
        </div>
        <p className="mt-1 text-right text-[0.6rem] text-[var(--hermes-muted)]">62% · ETA 2 days</p>
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {[
          { label: "Departed", active: false },
          { label: "In transit", active: true },
          { label: "On schedule", active: false },
        ].map((s) => (
          <div
            key={s.label}
            className={`rounded px-2 py-1.5 text-center text-[0.58rem] ${
              s.active
                ? "bg-[var(--hermes-indigo-soft)] text-[var(--hermes-indigo)]"
                : "bg-[var(--hermes-panel-strong)] text-[var(--hermes-muted)]"
            }`}
          >
            {s.label}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Data ─────────────────────────────────────────────────────

const MOCKUP_ORDERS = [
  { id: "ORD-0041", client: "Acme Logistics", route: "MAD → CDG", statusLabel: "Confirmed", statusColor: "#34d399" },
  { id: "ORD-0040", client: "BuildCorp GmbH", route: "BER → WAW", statusLabel: "Searching", statusColor: "#a78bfa" },
  { id: "ORD-0039", client: "FastCargo Ltd", route: "RTM → MXP", statusLabel: "Pending", statusColor: "#fb923c" },
];

const featureCards = [
  {
    title: "Smart intake",
    copy: "Extract structured order data from emails and documents. Review and correct before it enters your workflow.",
    preview: <IntakePreview />,
  },
  {
    title: "Carrier match",
    copy: "Score and compare carriers against your route, cargo type, and budget. Pick the best fit in one click.",
    preview: <CarrierMatchPreview />,
  },
  {
    title: "Contextual assistant",
    copy: "Ask questions about your orders, carriers, or shipments. The assistant answers with your operational context.",
    preview: <SmartCommsPreview />,
  },
  {
    title: "Shipment tracking",
    copy: "Monitor every active shipment with progress updates, alerts, and estimated delivery times.",
    preview: <TrackingPreview />,
  },
];

// ─── Animated hero mockup ─────────────────────────────────────

function HeroMockup() {
  const [visibleCount, setVisibleCount] = useState(0);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    let t: ReturnType<typeof setTimeout>;

    if (exiting) {
      // fade-out duration, then reset
      t = setTimeout(() => {
        setExiting(false);
        setVisibleCount(0);
      }, 500);
    } else if (visibleCount < MOCKUP_ORDERS.length) {
      // reveal next order
      t = setTimeout(
        () => setVisibleCount((n) => n + 1),
        visibleCount === 0 ? 600 : 750,
      );
    } else {
      // all visible — pause, then start exit
      t = setTimeout(() => setExiting(true), 2800);
    }

    return () => clearTimeout(t);
  }, [visibleCount, exiting]);

  return (
    <div className="flex overflow-hidden rounded-xl border border-[var(--hermes-border)]">
      {/* Mini sidebar */}
      <div className="w-32 shrink-0 border-r border-[var(--hermes-border)] bg-[var(--hermes-panel)] p-3">
        <div className="mb-5 px-2">
          <span className="text-[0.56rem] font-bold uppercase tracking-[0.22em] text-[var(--hermes-accent)]">
            HERMES
          </span>
        </div>
        <div className="space-y-0.5">
          {[
            { label: "Dashboard", active: false },
            { label: "Orders", active: true },
            { label: "Intake", active: false },
            { label: "Carriers", active: false },
          ].map((item) => (
            <div
              key={item.label}
              className={`flex items-center gap-2 rounded-lg px-2 py-2 text-[0.64rem] ${
                item.active
                  ? "bg-[var(--hermes-accent-soft)] font-medium text-[var(--hermes-accent)]"
                  : "text-[var(--hermes-muted)]"
              }`}
            >
              <span
                className="h-2 w-2 shrink-0 rounded-sm"
                style={{
                  backgroundColor: item.active
                    ? "var(--hermes-accent)"
                    : "rgba(124,124,138,0.28)",
                }}
              />
              {item.label}
            </div>
          ))}
        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 bg-[var(--hermes-bg)] p-4">
        {/* Page header */}
        <div className="mb-4">
          <p className="text-[0.56rem] uppercase tracking-[0.22em] text-[var(--hermes-muted)]">
            Operations
          </p>
          <p className="text-sm font-semibold text-[var(--hermes-text)]">Orders</p>
        </div>

        {/* Stats strip — counter synced with visible orders */}
        <div className="mb-4 flex gap-2">
          <div className="rounded-lg border border-[var(--hermes-border)] bg-[var(--hermes-panel)] px-3 py-2">
            <p className="text-[0.56rem] text-[var(--hermes-muted)]">Active orders</p>
            <p
              className="text-base font-semibold text-[var(--hermes-text)] tabular-nums transition-all duration-300"
              style={{ opacity: exiting ? 0 : 1 }}
            >
              {visibleCount}
            </p>
          </div>
          <div className="rounded-lg border border-[var(--hermes-accent)]/20 bg-[var(--hermes-accent-soft)] px-3 py-2">
            <p className="text-[0.56rem] text-[var(--hermes-accent)]">Needs attention</p>
            <p className="text-base font-semibold text-[var(--hermes-text)]">3</p>
          </div>
        </div>

        {/* Orders table */}
        <div className="overflow-hidden rounded-xl border border-[var(--hermes-border)] bg-[var(--hermes-panel)]">
          <div className="border-b border-[var(--hermes-border)] px-4 py-2.5">
            <p className="text-[0.58rem] font-medium uppercase tracking-[0.22em] text-[var(--hermes-muted)]">
              Latest orders
            </p>
          </div>
          <div className="divide-y divide-[var(--hermes-border)]">
            {MOCKUP_ORDERS.map((order, i) => {
              const isVisible = !exiting && i < visibleCount;
              return (
                <div
                  key={order.id}
                  className="flex items-center gap-3 px-4 py-2.5"
                  style={{
                    opacity: isVisible ? 1 : 0,
                    transform: isVisible ? "translateY(0)" : "translateY(8px)",
                    transition: exiting
                      ? "opacity 400ms ease, transform 400ms ease"
                      : "opacity 300ms ease, transform 300ms ease",
                  }}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[0.68rem] font-medium text-[var(--hermes-text)]">
                      {order.client}
                    </p>
                    <p className="text-[0.58rem] text-[var(--hermes-muted)]">{order.route}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <span
                      className="h-1.5 w-1.5 rounded-full"
                      style={{ backgroundColor: order.statusColor }}
                    />
                    <span
                      className="text-[0.58rem] font-medium"
                      style={{ color: order.statusColor }}
                    >
                      {order.statusLabel}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────

export function LandingPage() {
  const { isLoaded, isSignedIn } = useAuth();
  const isSignedInOperator = isLoaded && isSignedIn;
  const ctaHref = isSignedInOperator ? "/dashboard" : "/sign-up";

  return (
    <main className="min-h-screen bg-[var(--hermes-bg)] text-white">
      <div className="mx-auto flex min-h-screen w-full max-w-[1800px] flex-col px-6 pb-10 pt-6 md:px-10 lg:px-20">

        {/* ── Header ── */}
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-white/[0.06] px-5 py-3.5">
          <BrandLogo />
          <nav className="flex items-center gap-3">
            <a
              className="hidden text-sm text-slate-400 transition-colors hover:text-white lg:block"
              href="#features"
            >
              Features
            </a>
            <Link
              className="rounded-lg border border-white/10 bg-white/[0.03] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-white/[0.08]"
              to={isSignedInOperator ? "/dashboard" : "/sign-in"}
            >
              {isSignedInOperator ? "Open workspace" : "Sign in"}
            </Link>
          </nav>
        </header>

        {/* ── Hero ── */}
        <section className="grid flex-1 items-center gap-12 py-10 lg:grid-cols-[0.92fr_1.08fr] lg:py-12">
          <article className="max-w-2xl space-y-8">
            <div className="space-y-5">
              <p className="text-sm font-semibold uppercase tracking-[0.24em] text-[var(--hermes-accent)]">
                Hermes platform
              </p>
              <h1 className="text-5xl font-semibold leading-[1.08] tracking-tight text-white md:text-6xl lg:text-7xl">
                Freight forwarding,{" "}
                <span className="text-[var(--hermes-accent)]">orchestrated by agents</span>
              </h1>
              <p className="max-w-xl text-lg leading-8 text-slate-300">
                Move from inbound request to carrier booking inside one precise operator workflow.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-4">
              <Link className="hermes-primary-button inline-flex px-7 py-4 text-sm" to={ctaHref}>
                {isSignedInOperator ? "Go to dashboard" : "Start for free"}
              </Link>
            </div>
          </article>

          {/* Hero mockup — animated */}
          <aside className="hidden w-full rounded-2xl border border-white/[0.08] bg-[linear-gradient(180deg,#18181f,#131318)] p-3 shadow-[0_12px_48px_rgba(245,158,11,0.10)] transition-all duration-500 hover:-translate-y-1 hover:border-[var(--hermes-accent)]/20 hover:shadow-[0_24px_72px_rgba(245,158,11,0.22),0_0_0_1px_rgba(245,158,11,0.08)] lg:block">
            <HeroMockup />
          </aside>
        </section>

        {/* ── Divider ── */}
        <section className="border-t border-white/10 py-6" id="features">
          <p className="text-sm tracking-[0.18em] text-[var(--hermes-indigo)]">Driven by specialized AI agents</p>
        </section>

        {/* ── Feature cards ── */}
        <section className="grid gap-5 py-10 md:grid-cols-2">
          {featureCards.map((feature, i) => (
            <Reveal delay={i * 80} key={feature.title}>
              <article className="group flex h-full flex-col rounded-xl border border-white/[0.07] bg-[var(--hermes-bg-elevated)] p-8 shadow-[0_4px_24px_rgba(0,0,0,0.30)] transition-all duration-300 hover:-translate-y-1 hover:border-white/[0.14] hover:shadow-[0_12px_40px_rgba(0,0,0,0.45)]">
                <div className="mb-4 h-48 overflow-hidden">{feature.preview}</div>
                <div className="mt-auto space-y-3">
                  <h2 className="text-2xl font-semibold tracking-tight text-[#e8dfd4]">{feature.title}</h2>
                  <p className="max-w-md text-base leading-7 text-slate-400">{feature.copy}</p>
                </div>
              </article>
            </Reveal>
          ))}
        </section>

        {/* ── Footer ── */}
        <footer className="mt-6 flex flex-col gap-5 border-t border-white/10 py-8 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <BrandLogo />
            <p className="mt-3 max-w-xs text-sm leading-6 text-slate-500">
              Precise workflow control for freight-forwarding teams.
            </p>
          </div>
          <div className="text-left text-xs text-slate-600 sm:text-right">
            <p className="font-medium uppercase tracking-[0.12em] text-slate-500">Freight AI Platform</p>
            <p className="mt-1">© 2026 · MVP</p>
          </div>
        </footer>

      </div>
    </main>
  );
}
