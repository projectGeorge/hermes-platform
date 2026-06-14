import { Link } from "react-router-dom";

import { PageHeader } from "../../app/ui/PageHeader";
import { StateBlock } from "../../app/ui/StateBlock";
import { SurfacePanel } from "../../app/ui/SurfacePanel";
import { type DashboardLoadOrderSummary } from "../orders/api";
import { formatOrderStatusLabel } from "../orders/statusMeta";
import {
  useDashboardLoadOrderSummary,
  useAgentStatuses,
  useOrchestratorTimeline,
  type AgentStatus,
  type OrchestratorTimelineItem,
} from "../agents/api";

// ─── Status maps ──────────────────────────────────────────────────────────────

const SIMPLIFIED_STATE_LABELS: Record<string, string> = {
  running: "Working",
  awaiting_operator: "Needs operator",
  completed: "Idle",
  warning: "Attention",
  error: "Attention",
};

const ATTENTION_ACTIONS: Partial<Record<string, { label: string; href: (id: string) => string }>> = {
  pending_ingestion: { label: "Review intake", href: (id) => `/orders/${id}/intake` },
  viability_pending: { label: "Review intake", href: (id) => `/orders/${id}/intake` },
  viability_confirmed: { label: "Run carrier search", href: (id) => `/orders/${id}/carrier-match` },
  searching_carrier: { label: "Select carrier", href: (id) => `/orders/${id}/carrier-match` },
  ready_for_formalization: { label: "Formalize order", href: (id) => `/orders/${id}` },
};

const STATUS_DOT: Partial<Record<string, string>> = {
  pending_ingestion: "bg-[var(--hermes-accent)]",
  viability_pending: "bg-slate-500",
  viability_confirmed: "bg-emerald-400/70",
  searching_carrier: "bg-[var(--hermes-agent)]",
  ready_for_formalization: "bg-amber-400",
  formalized: "bg-emerald-400",
};

// Status text colors for the sidebar order list — readable, semantically mapped
const STATUS_TEXT_COLOR: Partial<Record<string, string>> = {
  pending_ingestion:       "text-[var(--hermes-accent)]",
  viability_pending:       "text-slate-500",
  viability_confirmed:     "text-emerald-400/80",
  ready_for_formalization: "text-amber-300",
  formalized:              "text-emerald-400/80",
  searching_carrier:       "text-[var(--hermes-indigo)]",
  cancelled:               "text-slate-600",
};

const RECENT_ACTIVITY_WINDOW_MS = 2 * 60 * 1000;

function getAgentGridClass(total: number) {
  if (total === 5) {
    return "grid auto-rows-fr grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-12 2xl:grid-cols-5";
  }

  if (total === 4) {
    return "grid auto-rows-fr grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4";
  }

  if (total === 3) {
    return "grid auto-rows-fr grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3";
  }

  if (total === 2) {
    return "grid auto-rows-fr grid-cols-1 gap-3 sm:grid-cols-2";
  }

  return "grid auto-rows-fr grid-cols-1 gap-3";
}

function getAgentCardSpanClass(index: number, total: number) {
  if (total !== 5) {
    return "";
  }

  return `${index < 3 ? "lg:col-span-4" : "lg:col-span-6"} 2xl:col-span-1`;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function AgentStatusCard({ agent }: { agent: AgentStatus }) {
  const isIdle = agent.state === "completed";
  const lastActivityTimestamp = agent.last_activity_at
    ? new Date(agent.last_activity_at).getTime()
    : null;
  const hasRecentActivity = lastActivityTimestamp !== null
    && Date.now() - lastActivityTimestamp < RECENT_ACTIVITY_WINDOW_MS;
  const isQuietIdle = isIdle && !hasRecentActivity;

  const stateColors: Record<string, string> = {
    running:           "border-[var(--hermes-agent)]/30 bg-[var(--hermes-agent-soft)]",
    completed:         "border-white/5",
    awaiting_operator: "border-amber-400/30 bg-amber-400/10",
    warning:           "border-amber-400/30 bg-amber-400/10",
    error:             "border-rose-400/30 bg-rose-400/10",
  };

  const stateDots: Record<string, string> = {
    running:           "bg-[var(--hermes-agent)] animate-pulse",
    completed:         "bg-white/15",
    awaiting_operator: "bg-amber-400",
    warning:           "bg-amber-400",
    error:             "bg-rose-400",
  };

  const simplifiedLabel = SIMPLIFIED_STATE_LABELS[agent.state] ?? agent.state;
  const cardTone = agent.state === "completed" && hasRecentActivity
    ? "border-white/10 bg-white/[0.03]"
    : (stateColors[agent.state] ?? "border-white/5");
  const dotTone = agent.state === "completed" && hasRecentActivity
    ? "bg-white/35"
    : (stateDots[agent.state] ?? "bg-white/15");

  return (
    <SurfacePanel className={`flex h-full flex-col border p-4 ${cardTone}`}>
      <div className="flex items-center gap-2">
        <span className={`h-1.5 w-1.5 rounded-full ${dotTone}`} />
        <p className={`text-[0.68rem] font-medium uppercase tracking-wider ${isQuietIdle ? "text-slate-500" : "text-slate-400"}`}>
          {agent.display_name}
        </p>
      </div>
      <p className={`mt-2 text-sm font-medium leading-snug ${isQuietIdle ? "text-slate-500" : "text-white"}`}>
        {agent.headline}
      </p>
      <div className="mt-1.5 flex items-center gap-2">
        <span className={`text-xs ${isQuietIdle ? "text-slate-600" : "text-slate-500"}`}>{simplifiedLabel}</span>
        {agent.last_activity_at ? (
          <span className="text-xs text-slate-600">
            · {new Date(agent.last_activity_at).toLocaleTimeString()}
          </span>
        ) : null}
      </div>
    </SurfacePanel>
  );
}

function TimelineRow({ item }: { item: OrchestratorTimelineItem }) {
  const agentColors: Record<string, string> = {
    orchestrator:   "text-[var(--hermes-agent)]",
    ingestion:      "text-[var(--hermes-data)]",
    carrier_search: "text-emerald-300",
    smart_comms:    "text-amber-300",
    monitoring:     "text-[var(--hermes-indigo)]",
  };

  return (
    <tr className="border-b border-white/5 transition-colors hover:bg-white/[0.015]">
      <td className="px-4 py-3">
        <span className={`text-xs font-medium uppercase tracking-wide ${agentColors[item.agent] ?? "text-slate-400"}`}>
          {item.agent.replace(/_/g, " ")}
        </span>
      </td>
      <td className="px-4 py-3">
        <p className="text-sm text-white">{item.title}</p>
        {item.detail ? <p className="mt-0.5 text-xs text-slate-500">{item.detail}</p> : null}
        {item.next_action ? (
          <p className="mt-1 text-xs text-[var(--hermes-accent)]">Next: {item.next_action}</p>
        ) : null}
      </td>
      <td className="px-4 py-3 text-sm text-slate-400">
        {item.customer_name ?? "—"}
      </td>
      <td className="px-4 py-3 text-xs text-slate-500">
        {new Date(item.created_at).toLocaleTimeString()}
      </td>
    </tr>
  );
}

function WorkflowStatusPanel({
  summary,
  isLoading,
}: {
  summary: DashboardLoadOrderSummary | undefined;
  isLoading: boolean;
}) {
  const activeOrders = summary?.recent_active_orders ?? [];
  const needsAttention = summary?.attention_orders ?? [];
  const attentionOrders = needsAttention.filter((order) => Boolean(ATTENTION_ACTIONS[order.status]));
  const needsAttentionCount = summary?.needs_attention_count ?? 0;
  const extraAttentionCount = Math.max(0, needsAttentionCount - attentionOrders.length);

  const header = (
    <div className="flex items-start justify-between gap-3 lg:flex-col lg:items-start lg:gap-2 2xl:flex-row 2xl:items-start 2xl:gap-3">
      <p className="text-[0.7rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
        Workflow status
      </p>
      <Link
        className="shrink-0 text-xs text-slate-600 transition-colors hover:text-slate-400"
        to="/orders"
      >
        All orders →
      </Link>
    </div>
  );

  const metrics = (
    <div className="grid grid-cols-2 gap-x-6 gap-y-3 lg:grid-cols-1 2xl:grid-cols-2">
      <div>
        <p className="text-2xl font-semibold text-white">{summary?.active_order_count ?? 0}</p>
        <p className="text-xs text-[var(--hermes-muted)]">Active orders</p>
      </div>
      <div>
        <p className={`text-2xl font-semibold ${needsAttentionCount > 0 ? "text-[var(--hermes-warning)]" : "text-white"}`}>
          {needsAttentionCount}
        </p>
        <p className="text-xs text-[var(--hermes-muted)]">Needs action</p>
      </div>
    </div>
  );

  if (isLoading) {
    return (
      <SurfacePanel className="overflow-hidden lg:h-[20rem] 2xl:h-[calc(100vh-16rem)] 2xl:max-h-[48rem]">
        <div className="flex h-full min-h-0 flex-col gap-5 lg:grid lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-6 2xl:grid-cols-1 2xl:gap-5">
          <div className="flex flex-col gap-4">
            {header}
            {metrics}
          </div>

          <div className="min-h-0 border-t border-[var(--hermes-border)] pt-4 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0 2xl:border-l-0 2xl:border-t 2xl:pl-0 2xl:pt-4">
            <div className="space-y-1">
              <div className="h-3 w-28 animate-pulse rounded bg-white/[0.06]" />
              {Array.from({ length: 4 }).map((_, index) => (
                <div key={index} className="grid gap-2 rounded-md border border-white/5 px-2 py-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                  <div className="space-y-2">
                    <div className="h-3 w-40 animate-pulse rounded bg-white/[0.06]" />
                    <div className="h-2 w-32 animate-pulse rounded bg-white/[0.04]" />
                  </div>
                  <div className="h-3 w-24 animate-pulse rounded bg-white/[0.05]" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </SurfacePanel>
    );
  }

  return (
    <SurfacePanel className="overflow-hidden lg:h-[20rem] 2xl:h-[calc(100vh-16rem)] 2xl:max-h-[48rem]">
      <div className="flex h-full min-h-0 flex-col gap-5 lg:grid lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-6 2xl:grid-cols-1 2xl:gap-5">
        <div className="flex flex-col gap-4">
          {header}
          {metrics}
        </div>

        <div className="min-h-0 border-t border-[var(--hermes-border)] pt-4 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0 2xl:border-l-0 2xl:border-t 2xl:pl-0 2xl:pt-4">
          {needsAttentionCount > 0 ? (
            <div className="flex h-full min-h-0 flex-col">
              <p className="mb-2 text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-warning)]">
                Needs action
              </p>
              {attentionOrders.length > 0 ? (
                <div className="min-h-0 space-y-1 overflow-y-auto pr-1">
                  {attentionOrders.map((order) => {
                    const action = ATTENTION_ACTIONS[order.status];
                    if (!action) return null;
                    const routeLabel = `${order.origin_text ?? "-"} → ${order.destination_text ?? "-"}`;
                    return (
                      <Link
                        key={order.id}
                        className="grid gap-2 rounded-md px-2 py-2 transition-colors hover:bg-white/[0.04] sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
                        to={action.href(order.id)}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm text-white">{order.customer_name ?? order.id}</p>
                          <p className="mt-0.5 truncate text-xs text-slate-500">{routeLabel}</p>
                        </div>
                        <span className="shrink-0 text-xs text-[var(--hermes-accent)]">
                          {action.label} →
                        </span>
                      </Link>
                    );
                  })}
                  {extraAttentionCount > 0 ? (
                    <p className="px-2 pt-1 text-xs text-[var(--hermes-muted)]">
                      +{extraAttentionCount} more in orders list
                    </p>
                  ) : null}
                </div>
              ) : (
                <p className="text-sm text-[var(--hermes-muted)]">Review the orders list for items needing action.</p>
              )}
            </div>
          ) : (
            <div className="flex h-full min-h-0 flex-col">
              <p className="mb-2 text-[0.65rem] font-medium uppercase tracking-widest text-emerald-500/70">
                All workflows clear
              </p>
              {activeOrders.length > 0 ? (
                <div className="min-h-0 space-y-1 overflow-y-auto pr-1">
                  {activeOrders.map((order) => {
                    const routeLabel = `${order.origin_text ?? "-"} → ${order.destination_text ?? "-"}`;
                    return (
                      <Link
                        key={order.id}
                        className="grid gap-2 rounded-md px-2 py-2 transition-colors hover:bg-white/[0.04] sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
                        to={`/orders/${order.id}`}
                      >
                        <div className="flex min-w-0 items-start gap-2.5">
                          <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${STATUS_DOT[order.status] ?? "bg-slate-500"}`} />
                          <div className="min-w-0">
                            <p className="truncate text-sm text-slate-200">{order.customer_name ?? order.id}</p>
                            <p className="mt-0.5 truncate text-xs text-slate-500">{routeLabel}</p>
                          </div>
                        </div>
                        <span className={`shrink-0 text-xs capitalize ${STATUS_TEXT_COLOR[order.status] ?? "text-slate-500"}`}>
                          {formatOrderStatusLabel(order.status)}
                        </span>
                      </Link>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-[var(--hermes-muted)]">No active orders right now.</p>
              )}
            </div>
          )}
        </div>
      </div>
    </SurfacePanel>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function DashboardPage() {
  const { data: summary, isLoading, isError } = useDashboardLoadOrderSummary();
  const { data: agentStatuses, isLoading: isAgentStatusesLoading } = useAgentStatuses();
  const { data: timeline, isLoading: isTimelineLoading }            = useOrchestratorTimeline(10);
  const agentStatusItems = agentStatuses?.agents ?? [];
  const agentGridClass = getAgentGridClass(agentStatusItems.length || 5);

  const needsAttentionCount = summary?.needs_attention_count ?? 0;

  const dateLabel = new Date().toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  return (
    <section className="space-y-4">
      <PageHeader
        eyebrow={dateLabel}
        title="Dashboard"
        actions={
          <div className="flex items-center gap-3">
            {needsAttentionCount > 0 ? (
              <span className="rounded-md border border-[var(--hermes-accent)]/25 bg-[var(--hermes-accent-soft)] px-2 py-0.5 text-xs font-medium text-[var(--hermes-accent)]">
                {needsAttentionCount} need{needsAttentionCount === 1 ? "s" : ""} action
              </span>
            ) : null}
            <Link className="hermes-primary-button px-4 py-2 text-sm" to="/orders/new">
              New order
            </Link>
          </div>
        }
      />

      {isError ? <StateBlock tone="error" title="Failed to load dashboard" /> : null}

      {/* Agent status grid — immediate multi-agent state */}
      {isAgentStatusesLoading ? (
        <div className={agentGridClass}>
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className={getAgentCardSpanClass(i, 5)}>
              <div className="h-full animate-pulse rounded-xl border border-white/5 p-4">
                <div className="h-2 w-2/3 rounded bg-white/[0.06]" />
                <div className="mt-3 h-4 w-full rounded bg-white/[0.06]" />
                <div className="mt-2 h-3 w-1/2 rounded bg-white/[0.04]" />
              </div>
            </div>
          ))}
        </div>
      ) : agentStatusItems.length > 0 ? (
        <div className={agentGridClass}>
          {agentStatusItems.map((agent, index) => (
            <div key={agent.agent_kind} className={getAgentCardSpanClass(index, agentStatusItems.length)}>
              <AgentStatusCard agent={agent} />
            </div>
          ))}
        </div>
      ) : null}

      {/* Main content: timeline + sidebar */}
      <div className="grid gap-4 2xl:grid-cols-[minmax(0,2fr)_minmax(19rem,1fr)] 2xl:items-start">
        {/* Workflow timeline — dominant surface */}
        <div>
          <SurfacePanel className="flex overflow-hidden p-0 2xl:h-[calc(100vh-16rem)] 2xl:max-h-[48rem] 2xl:flex-col">
            <div className="border-b border-white/8 px-5 py-4">
              <p className="text-[0.7rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
                Agent activity
              </p>
              <h2 className="mt-0.5 text-base font-semibold text-white">Workflow timeline</h2>
            </div>

            {isTimelineLoading ? (
              <div className="divide-y divide-white/[0.05]">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="flex items-start gap-4 animate-pulse px-4 py-3">
                    <div className="h-3 w-20 rounded bg-white/[0.06]" />
                    <div className="flex-1 space-y-2">
                      <div className="h-3 w-3/4 rounded bg-white/[0.06]" />
                      <div className="h-2 w-1/2 rounded bg-white/[0.04]" />
                    </div>
                    <div className="h-3 w-16 rounded bg-white/[0.04]" />
                    <div className="h-3 w-12 rounded bg-white/[0.04]" />
                  </div>
                ))}
              </div>
            ) : timeline && timeline.length > 0 ? (
              <div className="min-h-0 flex-1 overflow-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="sticky top-0 z-10 bg-[var(--hermes-panel)] text-xs text-slate-500">
                    <tr>
                      <th className="px-4 py-3 font-medium">Agent</th>
                      <th className="px-4 py-3 font-medium">Event</th>
                      <th className="px-4 py-3 font-medium">Customer</th>
                      <th className="px-4 py-3 font-medium">Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {timeline.map((item, i) => (
                      <TimelineRow key={i} item={item} />
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-5">
                <StateBlock
                  description="Workflow events will appear here as orders move through the system."
                  title="No agent activity yet"
                  tone="empty"
                />
              </div>
            )}
          </SurfacePanel>
        </div>

        {/* Sidebar: workflow status */}
        <WorkflowStatusPanel isLoading={isLoading} summary={summary} />
      </div>
    </section>
  );
}
