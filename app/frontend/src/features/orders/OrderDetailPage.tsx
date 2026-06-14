import { useAuth } from "@clerk/react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "../../app/ui/ConfirmDialog";
import { PageHeader } from "../../app/ui/PageHeader";
import { StateBlock } from "../../app/ui/StateBlock";
import { StatusBadge } from "../../app/ui/StatusBadge";
import { WorkspaceLoader } from "../../app/ui/WorkspaceLoader";
import { useOrchestratorTimeline } from "../agents/api";
import { formatOrderStatusLabel } from "./statusMeta";
import { getOrder, useFormalizeOrder, useDeleteOrder, useCancelOrder } from "./api";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(value: string | null): string | null {
  if (!value) return null;
  try {
    const d = new Date(value);
    if (isNaN(d.getTime())) return value;
    return new Intl.DateTimeFormat("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  } catch {
    return value;
  }
}

// ─── Workflow stages ──────────────────────────────────────────────────────────

const WORKFLOW_STAGES = [
  { key: "intake",        label: "Intake",        statuses: ["pending_ingestion"] },
  { key: "viability",     label: "Viability",     statuses: ["viability_pending", "viability_confirmed"] },
  { key: "carrier_match", label: "Carrier Match", statuses: ["searching_carrier"] },
  { key: "formalization", label: "Formalization", statuses: ["ready_for_formalization"] },
  { key: "formalized",    label: "Formalized",    statuses: ["formalized"] },
] as const;

function getStageIndex(status: string): number {
  for (let i = 0; i < WORKFLOW_STAGES.length; i++) {
    if ((WORKFLOW_STAGES[i].statuses as readonly string[]).includes(status)) return i;
  }
  return 0;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function Field({ label, value }: { label: string; value: string | null }) {
  const isEmpty = value === null || value === "";
  return (
    <div className="flex items-baseline gap-4">
      <dt className="w-40 shrink-0 text-sm text-[var(--hermes-muted)]">{label}</dt>
      <dd className={`text-sm ${isEmpty ? "text-[var(--hermes-muted)]" : "text-[var(--hermes-text)]"}`}>
        {isEmpty ? "—" : value}
      </dd>
    </div>
  );
}

function WorkflowStepper({ status }: { status: string }) {
  const activeIdx = getStageIndex(status);
  return (
    <div>
      {WORKFLOW_STAGES.map((stage, i) => {
        const isCompleted = i < activeIdx;
        const isActive = i === activeIdx;
        return (
          <div key={stage.key} className="flex items-start gap-3">
            <div className="flex flex-col items-center">
              <div
                className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${
                  isActive
                    ? "bg-[var(--hermes-accent)]"
                    : isCompleted
                    ? "bg-emerald-400/50"
                    : "border border-white/20 bg-transparent"
                }`}
                style={isActive ? { boxShadow: "0 0 5px rgba(245, 158, 11, 0.5)" } : undefined}
              />
              {i < WORKFLOW_STAGES.length - 1 && (
                <div
                  className={`mt-1 h-3 w-px ${isCompleted ? "bg-emerald-400/20" : "bg-white/10"}`}
                />
              )}
            </div>
            <p
              className={`pb-0.5 text-sm leading-none ${
                isActive
                  ? "font-medium text-[var(--hermes-accent)]"
                  : isCompleted
                  ? "text-[var(--hermes-muted)]"
                  : "text-[var(--hermes-muted)]/60"
              }`}
            >
              {stage.label}
            </p>
          </div>
        );
      })}
    </div>
  );
}

function ActionRow({ label, to }: { label: string; to: string }) {
  return (
    <Link
      className="group -mx-2 flex items-center justify-between rounded-md px-2 py-2.5 transition-colors duration-150 hover:bg-[var(--hermes-accent-soft)]"
      to={to}
    >
      <span className="text-sm text-[var(--hermes-muted)] transition-colors duration-150 group-hover:text-[var(--hermes-text)]">
        {label}
      </span>
      <span className="text-base text-[var(--hermes-muted)] transition-all duration-150 group-hover:translate-x-0.5 group-hover:text-[var(--hermes-accent)]">
        →
      </span>
    </Link>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function OrderDetailPage() {
  const { orderId = "" } = useParams();
  const navigate = useNavigate();
  const { getToken } = useAuth();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);

  const orderQuery = useQuery({
    queryKey: ["orders", orderId],
    queryFn: () => getOrder(orderId, getToken),
    enabled: orderId.length > 0,
  });

  const formalizeOrderMutation = useFormalizeOrder(orderId);
  const deleteOrderMutation = useDeleteOrder();
  const cancelOrderMutation = useCancelOrder();
  const timelineQuery = useOrchestratorTimeline(3, orderId);

  if (!orderId) return <StateBlock tone="error" title="Missing order identifier" />;
  if (orderQuery.isLoading) return <WorkspaceLoader label="Loading order detail" />;
  if (orderQuery.isError || !orderQuery.data) return <StateBlock tone="error" title="Failed to load order detail" />;

  const order = orderQuery.data;
  const showMonitoringAction = order.status === "formalized";
  const canFormalize = order.status === "ready_for_formalization";
  const isViabilityConfirmed = order.status === "viability_confirmed";
  const canOpenCarrierMatch = ["viability_confirmed", "searching_carrier", "ready_for_formalization", "formalized"].includes(order.status);
  const canCancel = order.status !== "cancelled" && order.status !== "formalized";
  const missingFieldKeys = order.missing_fields ? Object.keys(order.missing_fields) : [];
  const orderTimeline = timelineQuery.data ?? [];

  return (
    <section className="space-y-5">
      <PageHeader
        eyebrow="Order workspace"
        title={order.customer_name ?? `Order ${order.id.slice(0, 8)}…`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Link
              className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 transition-colors duration-150 hover:border-white/20 hover:bg-white/[0.05]"
              to="/orders"
            >
              Back to orders
            </Link>
            <Link
              className="hermes-primary-button inline-flex px-4 py-2 text-sm"
              to={`/orders/${order.id}/edit`}
            >
              Edit order
            </Link>
            {canFormalize ? (
              <button
                className="hermes-secondary-button px-4 py-2 text-sm disabled:opacity-60"
                disabled={formalizeOrderMutation.isPending}
                onClick={() => formalizeOrderMutation.mutate()}
                type="button"
              >
                {formalizeOrderMutation.isPending ? "Formalizing..." : "Formalize order"}
              </button>
            ) : null}
          </div>
        }
      />

      {/* Status strip */}
      <div className="flex flex-wrap items-center gap-3">
        <span
          className="rounded-full"
          style={isViabilityConfirmed ? { boxShadow: "0 0 8px rgba(52, 211, 153, 0.3)" } : undefined}
        >
          <StatusBadge status={order.status} />
        </span>
        <span className="text-sm text-slate-400">
          {order.origin_text ?? "—"} → {order.destination_text ?? "—"}
        </span>
        {formalizeOrderMutation.isError ? (
          <span className="text-xs text-[var(--hermes-danger)]">Failed to formalize order.</span>
        ) : null}
      </div>

      {/* Main asymmetric two-column document */}
      <div className="border-t border-[var(--hermes-border)] pt-8">
        <div className="grid max-w-5xl grid-cols-1 gap-y-12 xl:items-start xl:grid-cols-[1fr_360px] xl:gap-x-0">

          {/* LEFT — Order data fields */}
          <div className="space-y-10 xl:pr-12">

            <section>
              <h2 className="mb-5 text-xs font-medium uppercase tracking-wider text-[var(--hermes-muted)]">
                Shipment
              </h2>
              <dl className="space-y-3.5">
                <Field label="Customer" value={order.customer_name} />
                <Field label="Origin" value={order.origin_text} />
                <Field label="Destination" value={order.destination_text} />
                <Field
                  label="Distance"
                  value={order.distance_km != null ? `${order.distance_km} km` : null}
                />
              </dl>
            </section>

            <section>
              <h2 className="mb-5 text-xs font-medium uppercase tracking-wider text-[var(--hermes-muted)]">
                Schedule
              </h2>
              <dl className="space-y-3.5">
                <Field label="Origin load" value={formatDate(order.origin_load_date)} />
                <Field label="Destination unload" value={formatDate(order.destination_unload_date)} />
              </dl>
            </section>

            <section>
              <h2 className="mb-5 text-xs font-medium uppercase tracking-wider text-[var(--hermes-muted)]">
                Cargo
              </h2>
              <dl className="space-y-3.5">
                <Field label="Description" value={order.cargo_description} />
                <Field
                  label="Weight"
                  value={order.weight_kg != null ? `${order.weight_kg} kg` : null}
                />
                <Field
                  label="Truck type"
                  value={order.truck_type_id != null ? String(order.truck_type_id) : null}
                />
                <Field label="ADR required" value={order.adr_required ? "Yes" : "No"} />
              </dl>
            </section>

            <section>
              <h2 className="mb-5 text-xs font-medium uppercase tracking-wider text-[var(--hermes-muted)]">
                Commercial
              </h2>
              <dl className="space-y-3.5">
                <Field
                  label="Customer price"
                  value={order.customer_price != null ? `${order.customer_price} ${order.currency}` : null}
                />
                <Field label="Selected trip" value={order.selected_trip_id} />
              </dl>
            </section>

            {/* Metadata footnote */}
            <p className="text-xs text-[var(--hermes-muted)]">
              Created {formatDate(order.created_at) ?? "—"} · Updated {formatDate(order.updated_at) ?? "—"} · {order.id.slice(0, 8)}…
            </p>

          </div>

          {/* RIGHT — Workflow panel */}
          <div className="space-y-5 xl:border-l xl:border-[var(--hermes-border)] xl:pl-10">

            {/* Workflow stepper */}
            <div>
              <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-[var(--hermes-muted)]">
                Workflow
              </h3>
              <WorkflowStepper status={order.status} />
            </div>

            <div className="border-t border-[var(--hermes-border)]" />

            {/* Sub-workspace navigation */}
            <div>
              <h3 className="mb-1 text-xs font-medium uppercase tracking-wider text-[var(--hermes-muted)]">
                Workspaces
              </h3>
              <div>
                <ActionRow label="Intake" to={`/orders/${order.id}/intake`} />
                {canOpenCarrierMatch ? (
                  <ActionRow label="Carrier Match" to={`/orders/${order.id}/carrier-match`} />
                ) : null}
                {showMonitoringAction && (
                  <ActionRow label="Monitoring" to={`/orders/${order.id}/monitoring`} />
                )}
              </div>
              {!canOpenCarrierMatch ? (
                <p className="mt-3 text-xs text-[var(--hermes-muted)]">
                  Carrier Match unlocks after viability is confirmed.
                </p>
              ) : null}
            </div>

            {/* Missing fields warning */}
            {missingFieldKeys.length > 0 && (
              <>
                <div className="border-t border-[var(--hermes-border)]" />
                <div>
                  <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-[var(--hermes-muted)]">
                    Incomplete Fields
                  </h3>
                  <div className="rounded-lg border border-[var(--hermes-warning)]/25 bg-[var(--hermes-warning)]/[0.06] px-3 py-2.5">
                    <p className="mb-1.5 text-xs font-medium text-[var(--hermes-warning)]">
                      {missingFieldKeys.length} field{missingFieldKeys.length !== 1 ? "s" : ""} outstanding
                    </p>
                    <ul className="space-y-0.5">
                      {missingFieldKeys.map((k) => (
                        <li key={k} className="text-xs text-[var(--hermes-muted)]">
                          {k.replaceAll("_", " ")}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </>
            )}

            {/* Orchestrator activity — only renders when real entries exist for this order */}
            {orderTimeline.length > 0 && (
              <>
                <div className="border-t border-[var(--hermes-border)]" />
                <div>
                  <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-[var(--hermes-muted)]">
                    Recent Activity
                  </h3>
                  <div className="space-y-3.5">
                    {orderTimeline.map((item, i) => (
                      <div key={i} className="space-y-0.5">
                        <p className="text-xs leading-snug text-[var(--hermes-text)]/80">{item.title}</p>
                        {item.detail && (
                          <p className="text-xs leading-snug text-[var(--hermes-muted)]">{item.detail}</p>
                        )}
                        <p className="text-xs text-[var(--hermes-muted)]">
                           {formatDate(item.created_at)}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            <>
              <div className="border-t border-[var(--hermes-border)]" />
              <div>
                <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-[var(--hermes-muted)]">
                  Status model
                </h3>
                <p className="text-sm leading-relaxed text-[var(--hermes-muted)]">
                  Order workflow status is <span className="text-[var(--hermes-text)]">{formatOrderStatusLabel(order.status)}</span>.
                  Shipment execution starts only after formalization and continues in Monitoring.
                </p>
              </div>
            </>

            <div className="border-t border-[var(--hermes-border)]" />
            <div className="flex flex-col gap-2">
              {canCancel ? (
                <button
                  className="flex items-center gap-2 rounded-lg border border-amber-500/20 px-3 py-2 text-sm text-amber-400 transition-colors duration-150 hover:border-amber-500/40 hover:bg-amber-500/10"
                  onClick={() => setShowCancelConfirm(true)}
                  type="button"
                >
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                    <path d="M18.364 18.364A9 9 0 0 0 5.636 5.636m12.728 12.728A9 9 0 0 1 5.636 5.636m12.728 12.728L5.636 5.636" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  Cancel order
                </button>
              ) : null}
              <button
                className="flex items-center gap-2 rounded-lg border border-red-500/20 px-3 py-2 text-sm text-red-400 transition-colors duration-150 hover:border-red-500/40 hover:bg-red-500/10"
                onClick={() => setShowDeleteConfirm(true)}
                type="button"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                  <path d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Delete order
              </button>
            </div>

          </div>
        </div>
      </div>

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Delete order permanently"
        description={`This will permanently delete the order for "${order.customer_name ?? order.id.slice(0, 8)}". This action cannot be undone and will remove all associated data including ingestion runs, carrier proposals, and activity history.`}
        confirmLabel="Delete permanently"
        tone="danger"
        isBusy={deleteOrderMutation.isPending}
        onConfirm={() => {
          setShowDeleteConfirm(false);
          deleteOrderMutation.mutate(orderId, {
            onSuccess: () => {
              navigate("/orders");
            },
          });
        }}
        onCancel={() => setShowDeleteConfirm(false)}
      />

      <ConfirmDialog
        open={showCancelConfirm}
        title="Cancel order"
        description={`This will cancel the order for "${order.customer_name ?? order.id.slice(0, 8)}". The order will be marked as cancelled and removed from the active workflow. You can still view it in the orders list.`}
        confirmLabel="Cancel order"
        tone="danger"
        isBusy={cancelOrderMutation.isPending}
        onConfirm={() => {
          setShowCancelConfirm(false);
          cancelOrderMutation.mutate(orderId);
        }}
        onCancel={() => setShowCancelConfirm(false)}
      />
    </section>
  );
}
