import { useAuth } from "@clerk/react";
import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ConfirmDialog } from "../../app/ui/ConfirmDialog";
import { PageHeader } from "../../app/ui/PageHeader";
import { StateBlock } from "../../app/ui/StateBlock";
import { StatusBadge } from "../../app/ui/StatusBadge";
import { SurfacePanel } from "../../app/ui/SurfacePanel";

import { listOrdersPage, useDeleteOrder } from "./api";

function formatDate(value: string | null): string | null {
  if (!value) return null;
  try {
    const d = new Date(value);
    if (isNaN(d.getTime())) return value;
    return new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  } catch {
    return value;
  }
}

const ORDERS_PAGE_SIZE = 20;

export function OrdersListPage() {
  const { getToken } = useAuth();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState("");
  const [scope, setScope] = useState<"all" | "active">("all");
  const [page, setPage] = useState(0);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; label: string } | null>(null);
  const deferredSearchQuery = useDeferredValue(searchQuery);
  const deleteMutation = useDeleteOrder();

  useEffect(() => {
    setPage(0);
  }, [scope, deferredSearchQuery]);

  const { data: ordersPage, isLoading, isError } = useQuery({
    queryKey: ["orders", "page", page, scope, deferredSearchQuery],
    queryFn: () =>
      listOrdersPage(getToken, {
        skip: page * ORDERS_PAGE_SIZE,
        limit: ORDERS_PAGE_SIZE,
        activeOnly: scope === "active",
        search: deferredSearchQuery,
      }),
    placeholderData: (previousData) => previousData,
  });

  const orders = ordersPage?.items ?? [];
  const totalOrders = ordersPage?.total ?? 0;
  const currentPage = page + 1;
  const totalPages = Math.max(1, Math.ceil(totalOrders / ORDERS_PAGE_SIZE));
  const canGoPrevious = page > 0;
  const canGoNext = (ordersPage?.skip ?? 0) + ORDERS_PAGE_SIZE < totalOrders;

  return (
    <section className="space-y-4">
      <PageHeader
        eyebrow="Order management"
        title="Orders"
        actions={
          <Link className="hermes-primary-button px-4 py-2 text-sm" to="/orders/new">
            New order
          </Link>
        }
      />

      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-2">
          <button
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors duration-150 ${scope === "all" ? "bg-[var(--hermes-accent-soft)] text-[var(--hermes-accent)]" : "border border-white/10 text-slate-300 hover:bg-white/[0.06] hover:border-white/20"}`}
            onClick={() => setScope("all")}
            type="button"
          >
            All orders
          </button>
          <button
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors duration-150 ${scope === "active" ? "bg-[var(--hermes-accent-soft)] text-[var(--hermes-accent)]" : "border border-white/10 text-slate-300 hover:bg-white/[0.06] hover:border-white/20"}`}
            onClick={() => setScope("active")}
            type="button"
          >
            Active orders
          </button>
        </div>

        <label className="block w-full lg:max-w-sm">
          <span className="sr-only">Search by order, client, or route</span>
          <input
            className="hermes-input"
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search by order, client, or route"
            type="search"
            value={searchQuery}
          />
        </label>
      </div>

      {isError ? <StateBlock tone="error" title="Failed to load orders" /> : null}

      {!isError ? (
        <SurfacePanel className="flex max-h-[calc(100vh-14rem)] flex-col overflow-hidden p-0 lg:max-h-[calc(100vh-12.5rem)]">
          {isLoading ? (
            <div className="divide-y divide-white/[0.06]">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex items-center gap-4 animate-pulse px-4 py-3">
                  <div className="h-3 w-16 rounded bg-white/[0.06]" />
                  <div className="h-3 w-28 rounded bg-white/[0.06]" />
                  <div className="h-3 flex-1 rounded bg-white/[0.05]" />
                  <div className="h-5 w-20 rounded-full bg-white/[0.05]" />
                  <div className="h-7 w-24 rounded-lg bg-white/[0.04]" />
                </div>
              ))}
            </div>
          ) : orders.length > 0 ? (
            <>
              <div className="min-h-0 flex-1 overflow-auto">
                <table className="min-w-full divide-y divide-white/8 text-left text-sm text-slate-200">
                  <thead className="sticky top-0 z-10 bg-[var(--hermes-panel)] text-xs text-slate-500">
                    <tr>
                      <th className="px-4 py-3 font-medium">Order</th>
                      <th className="px-4 py-3 font-medium">Client</th>
                      <th className="px-4 py-3 font-medium">Created</th>
                      <th className="px-4 py-3 font-medium">Route</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="px-4 py-3 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/8">
                    {orders.map((order) => (
                      <tr key={order.id} className="transition-colors duration-150 hover:bg-white/[0.025]">
                        <td className="px-4 py-3">
                          <span
                            className="font-mono text-xs text-slate-300"
                            title={order.id}
                          >
                            {order.id.slice(0, 8)}…
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {order.customer_name
                            ? <span className="text-slate-200">{order.customer_name}</span>
                            : <span className="italic text-[var(--hermes-muted)]">Unnamed</span>
                          }
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-xs text-slate-400">
                          {formatDate(order.created_at) ?? "—"}
                        </td>
                        <td className="px-4 py-3 text-slate-400">
                          {order.origin_text ?? "-"} → {order.destination_text ?? "-"}
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={order.status} />
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <Link
                              className="rounded-lg border border-white/20 bg-white/[0.05] px-3 py-2 text-sm text-white transition-colors duration-150 hover:bg-white/[0.09] hover:border-white/30"
                              to={`/orders/${order.id}`}
                            >
                              Open detail
                            </Link>
                            <Link
                              className="rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300 transition-colors duration-150 hover:bg-white/[0.05] hover:border-white/20"
                              to={`/orders/${order.id}/edit`}
                            >
                              Edit order
                            </Link>
                            <button
                              aria-label={`Delete order ${order.id.slice(0, 8)}`}
                              className="rounded-lg border border-white/10 p-2 text-slate-400 transition-colors duration-150 hover:border-red-500/30 hover:bg-red-500/10 hover:text-red-400"
                              onClick={() => setDeleteTarget({ id: order.id, label: order.customer_name ?? order.id.slice(0, 8) })}
                              title="Delete order"
                              type="button"
                            >
                              <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                                <path d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex shrink-0 items-center justify-between gap-3 border-t border-white/8 px-4 py-3 text-xs text-[var(--hermes-muted)]">
                <span>
                  Page {currentPage} of {totalPages} · {totalOrders} total order{totalOrders === 1 ? "" : "s"}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    className="rounded-lg border border-white/10 px-3 py-2 text-slate-300 transition-colors hover:bg-white/[0.05] hover:border-white/20 disabled:opacity-40"
                    disabled={!canGoPrevious}
                    onClick={() => setPage((current) => Math.max(0, current - 1))}
                    type="button"
                  >
                    Previous
                  </button>
                  <button
                    className="rounded-lg border border-white/10 px-3 py-2 text-slate-300 transition-colors hover:bg-white/[0.05] hover:border-white/20 disabled:opacity-40"
                    disabled={!canGoNext}
                    onClick={() => setPage((current) => current + 1)}
                    type="button"
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="p-6">
              <StateBlock tone="empty" title="No orders match the current filters" />
            </div>
          )}
        </SurfacePanel>
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete order permanently"
        description={`This will permanently delete the order for "${deleteTarget?.label ?? ""}". This action cannot be undone and will remove all associated data including ingestion runs, carrier proposals, and activity history.`}
        confirmLabel="Delete permanently"
        tone="danger"
        isBusy={deleteMutation.isPending}
        onConfirm={() => {
          if (!deleteTarget) return;
          const targetId = deleteTarget.id;
          setDeleteTarget(null);
          deleteMutation.mutate(targetId);
        }}
        onCancel={() => setDeleteTarget(null)}
      />
    </section>
  );
}
