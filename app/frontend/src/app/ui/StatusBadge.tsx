import { formatOrderStatusLabel, ORDER_STATUS_TONE } from "../../features/orders/statusMeta";

export function StatusBadge({ status }: { status: string }) {
  const tone = ORDER_STATUS_TONE[status] ?? "bg-white/5 text-slate-400";

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium ${tone}`}>
      <span className="size-1.5 shrink-0 rounded-full bg-current opacity-60" aria-hidden="true" />
      {formatOrderStatusLabel(status)}
    </span>
  );
}
