import { UserButton } from "@clerk/react";
import { useState } from "react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { BrandLogo } from "../ui/BrandLogo";
import { userButtonAppearance } from "../../features/auth/clerkAppearance";
import { useCurrentUserQuery } from "../../features/session/useCurrentUserQuery";
import { SmartCommsPanel } from "../../features/smart-comms/SmartCommsPanel";
import { useShellPageContext } from "./useShellPageContext";

// ─── Nav icons ───────────────────────────────────────────────────────────────

function DashboardIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24">
      <rect x="3" y="3" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.75" />
      <rect x="13" y="3" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.75" />
      <rect x="3" y="13" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.75" />
      <rect x="13" y="13" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.75" />
    </svg>
  );
}

function OrdersIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24">
      <rect x="4" y="3" width="16" height="18" rx="2" stroke="currentColor" strokeWidth="1.75" />
      <path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" strokeLinecap="round" strokeWidth="1.75" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.75" />
      <path
        d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.75"
      />
    </svg>
  );
}

function CollapseIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg
      className={`h-3.5 w-3.5 transition-transform duration-200 ${collapsed ? "rotate-180" : ""}`}
      fill="none"
      viewBox="0 0 24 24"
    >
      <path
        d="M15 19l-7-7 7-7"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

function MenuIcon() {
  return (
    <svg aria-hidden="true" className="h-5 w-5" fill="none" viewBox="0 0 24 24">
      <path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  );
}

function XIcon() {
  return (
    <svg aria-hidden="true" className="h-5 w-5" fill="none" viewBox="0 0 24 24">
      <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  );
}

// ─── Nav items ────────────────────────────────────────────────────────────────

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: <DashboardIcon /> },
  { to: "/orders", label: "Orders", icon: <OrdersIcon /> },
  { to: "/settings", label: "Settings", icon: <SettingsIcon /> },
];

function navClassName({ isActive }: { isActive: boolean }) {
  return [
    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-150",
    isActive
      ? "bg-[var(--hermes-accent-soft)] text-[var(--hermes-accent)]"
      : "text-[var(--hermes-muted)] hover:bg-white/[0.04] hover:text-white",
  ].join(" ");
}

function PrimaryNav({
  onSelect,
  collapsed,
  mobileNav,
}: {
  onSelect?: () => void;
  collapsed?: boolean;
  mobileNav?: boolean;
}) {
  return (
    <nav
      aria-label={mobileNav ? "Mobile navigation" : "Primary navigation"}
      className="flex flex-col gap-0.5 px-3 py-4"
    >
      {navItems.map((item) => (
        <NavLink
          key={item.to}
          className={navClassName}
          onClick={onSelect}
          title={collapsed ? item.label : undefined}
          to={item.to}
        >
          {item.icon}
          {!collapsed ? <span>{item.label}</span> : null}
        </NavLink>
      ))}
    </nav>
  );
}

// ─── AppShell ─────────────────────────────────────────────────────────────────

export function AppShell({ children }: { children: ReactNode }) {
  const { data: currentUser } = useCurrentUserQuery();
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const pageContext = useShellPageContext();
  const operatorName = currentUser?.operator_name ?? "…";

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--hermes-bg)] text-slate-50">
      {/* ── Sidebar: desktop navigation rail ─────────────────────────────── */}
      <aside
        className={`hidden shrink-0 flex-col border-r border-[var(--hermes-border)] bg-[var(--hermes-panel)] transition-[width] duration-200 md:flex ${
          isSidebarCollapsed ? "w-14" : "w-[220px]"
        }`}
      >
        {/* Brand header */}
        <div
          className={`flex h-14 shrink-0 items-center border-b border-[var(--hermes-border)] ${
            isSidebarCollapsed ? "justify-center px-3" : "px-4"
          }`}
        >
          <BrandLogo compact={isSidebarCollapsed} />
        </div>

        {/* Navigation */}
        <PrimaryNav collapsed={isSidebarCollapsed} />

        {/* Sidebar footer: operator identity + user button + collapse toggle */}
        <div className="mt-auto border-t border-[var(--hermes-border)] p-3">
          {!isSidebarCollapsed ? (
            <div className="mb-3 flex items-center justify-between gap-2 px-1">
              <div className="min-w-0">
                <p className="text-[0.64rem] uppercase tracking-widest text-[var(--hermes-muted)]">Operator</p>
                <p className="mt-0.5 truncate text-sm font-medium text-white">{operatorName}</p>
              </div>
              <UserButton appearance={userButtonAppearance} />
            </div>
          ) : (
            <div className="mb-3 flex justify-center">
              <UserButton appearance={userButtonAppearance} />
            </div>
          )}
          <button
            aria-label={isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-white/10 text-slate-400 transition-colors hover:bg-white/5 hover:text-white"
            onClick={() => setIsSidebarCollapsed((v) => !v)}
          >
            <CollapseIcon collapsed={isSidebarCollapsed} />
          </button>
        </div>
      </aside>

      {/* ── Right column: topbar (mobile only) + page content ────────────── */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Topbar — mobile only; desktop uses sidebar footer for identity/actions */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--hermes-border)] bg-[var(--hermes-panel)] px-4 md:hidden">
          <div className="flex items-center gap-2">
            <BrandLogo compact />
            <button
              aria-label="Toggle navigation"
              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-white/10 text-slate-300 transition-colors hover:text-white"
              onClick={() => setIsMobileNavOpen((v) => !v)}
              type="button"
            >
              {isMobileNavOpen ? <XIcon /> : <MenuIcon />}
            </button>
          </div>
          <UserButton appearance={userButtonAppearance} />
        </header>

        {/* Mobile nav drawer */}
        {isMobileNavOpen ? (
          <div className="border-b border-[var(--hermes-border)] bg-[var(--hermes-panel)] md:hidden">
            <PrimaryNav mobileNav onSelect={() => setIsMobileNavOpen(false)} />
          </div>
        ) : null}

        {/* Page content — only this region scrolls */}
        <main className="flex-1 overflow-y-auto px-5 py-5 pb-24 md:px-6 md:py-6 md:pb-28">
          {children}
        </main>
      </div>

      <SmartCommsPanel
        contextId={pageContext.contextId}
        contextType={pageContext.contextType}
        label={pageContext.label}
        routePath={pageContext.routePath}
      />
    </div>
  );
}
