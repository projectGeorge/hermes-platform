export const ORDER_STATUS_LABEL: Record<string, string> = {
  pending_ingestion: "Pending ingestion",
  viability_pending: "Viability pending",
  viability_confirmed: "Viability confirmed",
  searching_carrier: "Searching carrier",
  ready_for_formalization: "Ready to formalize",
  formalized: "Formalized",
  cancelled: "Cancelled",
};

export const ORDER_STATUS_TONE: Record<string, string> = {
  pending_ingestion:       "bg-slate-500/10 text-slate-400",
  viability_pending:       "bg-amber-500/10 text-amber-400",
  viability_confirmed:     "bg-teal-500/10 text-teal-400",
  searching_carrier:       "bg-blue-500/10 text-blue-400",
  ready_for_formalization: "bg-orange-500/10 text-orange-400",
  formalized:              "bg-emerald-500/10 text-emerald-400",
  cancelled:               "bg-rose-500/10 text-rose-400",
};

export function formatOrderStatusLabel(status: string) {
  return ORDER_STATUS_LABEL[status] ?? status.replaceAll("_", " ");
}
