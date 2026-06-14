import { Link, useParams } from "react-router-dom";

import { PageHeader } from "../../app/ui/PageHeader";
import { StateBlock } from "../../app/ui/StateBlock";
import type {
  ExecutionMonitoringAgentUpdate,
  ExecutionMonitoringSnapshot,
  MonitoringAlert,
} from "../orders/api";
import { RouteMap } from "./RouteMap";
import { useExecutionMonitoring, useRefreshExecutionMonitoring } from "./api";
import { WorkspaceLoader } from "../../app/ui/WorkspaceLoader";

// ─── Helpers ───────────────────────────────────────────────────────────────────

function formatTimestamp(value: string) {
  return new Date(value).toLocaleString();
}

function formatShortTime(value: string) {
  const d = new Date(value);
  return (
    d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) +
    " · " +
    d.toLocaleDateString([], { day: "2-digit", month: "short" })
  );
}

// ─── Monitoring status chip ────────────────────────────────────────────────────

function MonitoringStatusChip({ status, label }: { status: string; label: string }) {
  const tone =
    status === "in_transit"
      ? "border-[var(--hermes-data)]/30 text-[var(--hermes-data)] bg-[var(--hermes-data-soft)]"
      : status === "delayed"
        ? "border-amber-400/30 text-amber-400 bg-amber-400/[0.06]"
        : status === "delivered"
          ? "border-emerald-400/30 text-emerald-400 bg-emerald-400/[0.06]"
          : "border-white/10 text-[var(--hermes-muted)]";
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${tone}`}>
      {label}
    </span>
  );
}

// ─── Checkpoint pills ─────────────────────────────────────────────────────────

function CheckpointPills({ snapshot }: { snapshot: ExecutionMonitoringSnapshot }) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-[var(--hermes-border)] py-3">
      {snapshot.route_points.map((point) => {
        const tone =
          point.status === "completed"
            ? "border-emerald-400/30 text-emerald-400/80 bg-emerald-400/[0.05]"
            : point.status === "active"
              ? "border-[var(--hermes-data)]/30 text-[var(--hermes-data)] bg-[var(--hermes-data-soft)]"
              : "border-white/10 text-[var(--hermes-muted)]";
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-0.5 text-xs font-medium ${tone}`}
            key={`${point.kind}-${point.sequence}`}
          >
            {point.status === "completed" ? (
              <svg className="h-3 w-3 shrink-0" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path d="m5 13 4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            ) : null}
            {point.label}
          </span>
        );
      })}
    </div>
  );
}

// ─── Agent update ─────────────────────────────────────────────────────────────

function AgentUpdateSection({ agentUpdate }: { agentUpdate: ExecutionMonitoringAgentUpdate }) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
          Agent update
        </h2>
        <span className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-0.5 text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
          {agentUpdate.source}
        </span>
      </div>
      <p className="text-sm leading-relaxed text-[var(--hermes-text)]">{agentUpdate.summary}</p>
      {agentUpdate.incident_summary ? (
        <div className="rounded-lg border border-amber-400/20 bg-amber-400/[0.06] px-4 py-3">
          <p className="text-[0.65rem] font-medium uppercase tracking-widest text-amber-400/80">
            Incident summary
          </p>
          <p className="mt-1.5 text-xs leading-relaxed text-[var(--hermes-text)]">
            {agentUpdate.incident_summary}
          </p>
        </div>
      ) : null}
      {agentUpdate.operator_note ? (
        <p className="text-xs italic text-[var(--hermes-muted)]">{agentUpdate.operator_note}</p>
      ) : null}
      <p className="text-[0.65rem] text-[var(--hermes-muted)]">
        Generated {formatShortTime(agentUpdate.generated_at)}
      </p>
    </section>
  );
}

// ─── Incidents ────────────────────────────────────────────────────────────────

function alertTone(alert: MonitoringAlert) {
  if (alert.severity === "critical") return "border-rose-400/30 bg-rose-400/[0.06]";
  if (alert.severity === "warning") return "border-amber-400/30 bg-amber-400/[0.06]";
  return "border-[var(--hermes-border)] bg-white/[0.02]";
}

function IncidentsSection({ alerts }: { alerts: MonitoringAlert[] }) {
  return (
    <section className="space-y-3">
      <h2 className="text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
        Execution incidents
      </h2>
      {alerts.length > 0 ? (
        <div className="space-y-2">
          {alerts.map((alert) => (
            <article className={`rounded-lg border px-4 py-3 ${alertTone(alert)}`} key={alert.id}>
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-medium text-[var(--hermes-text)]">{alert.title}</p>
                <span className="shrink-0 text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
                  {alert.severity}
                </span>
              </div>
              {alert.detail ? (
                <p className="mt-1.5 text-xs leading-relaxed text-[var(--hermes-muted)]">{alert.detail}</p>
              ) : null}
              <p className="mt-2 text-[0.65rem] text-[var(--hermes-muted)]">
                {formatTimestamp(alert.created_at)}
              </p>
            </article>
          ))}
        </div>
      ) : (
        <p className="text-sm text-emerald-400/70">No active incidents.</p>
      )}
    </section>
  );
}

// ─── Timeline ────────────────────────────────────────────────────────────────

function eventAccent(severity: string) {
  if (severity === "warning") return "border-l-amber-300";
  if (severity === "critical") return "border-l-rose-300";
  return "border-l-[var(--hermes-indigo)]";
}

function TimelineSection({ snapshot }: { snapshot: ExecutionMonitoringSnapshot }) {
  const sorted = snapshot.events
    .slice()
    .sort((a, b) => new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime());

  return (
    <section className="space-y-3">
      <h2 className="text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
        Execution timeline
      </h2>
      {sorted.length > 0 ? (
        <div className="space-y-2">
          {sorted.map((event) => (
            <article
              className={`rounded-lg border border-white/[0.08] border-l-2 bg-white/[0.02] px-4 py-3 ${eventAccent(event.severity)}`}
              key={`${event.event_type}-${event.occurred_at}`}
            >
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-medium text-[var(--hermes-text)]">{event.title}</p>
                <span className="shrink-0 text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
                  {event.severity}
                </span>
              </div>
              {event.detail ? (
                <p className="mt-1.5 text-xs leading-relaxed text-[var(--hermes-muted)]">{event.detail}</p>
              ) : null}
              <p className="mt-2 text-[0.65rem] text-[var(--hermes-muted)]">
                {(event.checkpoint_name ?? event.event_type).replaceAll("_", " ")}
                {" · "}
                {formatTimestamp(event.occurred_at)}
              </p>
            </article>
          ))}
        </div>
      ) : (
        <p className="text-sm text-[var(--hermes-muted)]">No events persisted yet.</p>
      )}
    </section>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export function ExecutionMonitoringPage() {
  const { orderId = "" } = useParams();
  const monitoringQuery = useExecutionMonitoring(orderId);
  const refreshMonitoringMutation = useRefreshExecutionMonitoring(orderId);

  if (!orderId) {
    return <StateBlock tone="error" title="Missing order identifier" />;
  }

  if (monitoringQuery.isLoading) {
    return <WorkspaceLoader label="Loading shipment monitoring" />;
  }

  if (monitoringQuery.isError || !monitoringQuery.data) {
    return <StateBlock tone="error" title="Failed to load shipment monitoring" />;
  }

  const data = refreshMonitoringMutation.data ?? monitoringQuery.data;
  const { snapshot, alerts, shipment, agent_update: agentUpdate } = data;

  return (
    <section className="space-y-5">
      <PageHeader
        actions={
          <>
            <Link
              className="rounded-lg border border-white/10 px-4 py-2 text-sm text-[var(--hermes-text)] transition-colors hover:border-white/20 hover:bg-white/[0.04]"
              to={`/orders/${orderId}`}
            >
              Back to order
            </Link>
            <button
              className="hermes-primary-button px-4 py-2 text-sm disabled:opacity-60"
              disabled={refreshMonitoringMutation.isPending}
              onClick={() => refreshMonitoringMutation.mutate()}
              type="button"
            >
              {refreshMonitoringMutation.isPending ? "Refreshing…" : "Refresh monitoring"}
            </button>
          </>
        }
        eyebrow="Execution monitoring"
        title={shipment.route_label}
      />

      {/* ── Context strip ──────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-[var(--hermes-border)] pb-4">
        <dl className="flex flex-wrap gap-x-6 gap-y-1.5">
          {shipment.customer_name ? (
            <div>
              <dt className="text-xs text-[var(--hermes-muted)]">Customer</dt>
              <dd className="text-sm text-[var(--hermes-text)]">{shipment.customer_name}</dd>
            </div>
          ) : null}
          {shipment.carrier_name ? (
            <div>
              <dt className="text-xs text-[var(--hermes-muted)]">Carrier</dt>
              <dd className="text-sm text-[var(--hermes-text)]">{shipment.carrier_name}</dd>
            </div>
          ) : null}
          {shipment.cargo_description ? (
            <div>
              <dt className="text-xs text-[var(--hermes-muted)]">Cargo</dt>
              <dd className="text-sm text-[var(--hermes-text)]">{shipment.cargo_description}</dd>
            </div>
          ) : null}
          {shipment.distance_km ? (
            <div>
              <dt className="text-xs text-[var(--hermes-muted)]">Distance</dt>
              <dd className="text-sm text-[var(--hermes-text)]">{shipment.distance_km} km</dd>
            </div>
          ) : null}
        </dl>
        <div className="flex items-center gap-3">
          <span className="text-xs text-[var(--hermes-muted)]">
            via {shipment.last_update_source.replaceAll("_", " ")}
          </span>
          <MonitoringStatusChip label={shipment.current_status_label} status={snapshot.status} />
        </div>
      </div>

      {/* ── Progress strip ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-4 border-b border-[var(--hermes-border)] pb-4">
        <p className="shrink-0 text-sm font-medium text-[var(--hermes-text)]">
          {snapshot.current_position.label}
        </p>
        <div className="flex-1">
          <div className="h-1.5 rounded-full bg-white/[0.06]">
            <div
              className="h-1.5 rounded-full bg-[linear-gradient(90deg,#818cf8,#6366f1)]"
              style={{ width: `${Math.max(4, snapshot.progress_percent)}%` }}
            />
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <span className="text-sm font-semibold tabular-nums text-[var(--hermes-text)]">
            {snapshot.progress_percent}%
          </span>
          <span className="hidden text-xs text-[var(--hermes-muted)] sm:inline">
            Refreshed {formatShortTime(snapshot.last_refreshed_at)}
          </span>
        </div>
      </div>

      {/* ── Route map ─────────────────────────────────────────────────────── */}
      <RouteMap
        className="h-[420px]"
        currentPosition={snapshot.current_position}
        routePath={snapshot.route_path}
        routePoints={snapshot.route_points}
      />

      {/* ── Checkpoint pills ───────────────────────────────────────────────── */}
      <CheckpointPills snapshot={snapshot} />

      {/* ── Bottom: agent update · incidents · timeline ─────────────────── */}
      <div className="grid gap-6 xl:grid-cols-3">
        <AgentUpdateSection agentUpdate={agentUpdate} />
        <IncidentsSection alerts={alerts} />
        <TimelineSection snapshot={snapshot} />
      </div>
    </section>
  );
}
