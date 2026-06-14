import { useAuth } from "@clerk/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { PageHeader } from "../../app/ui/PageHeader";
import { StateBlock } from "../../app/ui/StateBlock";
import { StatusBadge } from "../../app/ui/StatusBadge";
import { WorkspaceLoader } from "../../app/ui/WorkspaceLoader";
import { ApiError } from "../../lib/apiClient";
import { getOrder, listTruckTypes } from "../orders/api";
import { formatOrderStatusLabel } from "../orders/statusMeta";
import {
  getCarrierCandidates,
  runCarrierSearch,
  selectCarrier,
  type CarrierCandidate,
} from "./api";

// ─── Helpers ───────────────────────────────────────────────────────────────────

function formatValue(value: string | number | boolean | null) {
  if (value === null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function formatMoney(value: string | null, currency: string) {
  if (value === null || value === "") return "—";
  return `${value} ${currency}`;
}

function formatMargin(value: string | null) {
  if (value === null || value === "") return "—";
  return value.startsWith("-") ? value : `+${value}`;
}

// ─── CandidateDetails accordion ────────────────────────────────────────────────

function CandidateDetails({
  candidate,
  truckName,
}: {
  candidate: CarrierCandidate;
  truckName: string | null;
}) {
  const [open, setOpen] = useState(false);
  const hasContent =
    candidate.agent_reasoning !== null ||
    candidate.ai_rejection_reason !== null ||
    truckName !== null ||
    candidate.score_breakdown !== null;

  if (!hasContent) return null;

  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-white/[0.08]">
      <button
        className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-xs font-medium text-[var(--hermes-muted)] transition-colors hover:bg-white/[0.03] hover:text-[var(--hermes-text)]"
        onClick={() => { setOpen((v) => !v); }}
        type="button"
      >
        <span>View details</span>
        {/* Chevron — rotates 180° when open */}
        <svg
          className="h-3.5 w-3.5 shrink-0 transition-transform duration-200"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)" }}
          viewBox="0 0 24 24"
        >
          <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {/* Animated reveal via grid-template-rows */}
      <div
        className="grid"
        style={{
          gridTemplateRows: open ? "1fr" : "0fr",
          transition: "grid-template-rows 0.22s ease",
        }}
      >
        <div className="overflow-hidden">
          <div className="space-y-4 border-t border-white/[0.06] px-4 py-4">
            {candidate.agent_reasoning ? (
              <div>
                <p className="text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
                  AI reasoning
                </p>
                <p className="mt-1.5 text-xs leading-relaxed text-[var(--hermes-text)]">
                  {candidate.agent_reasoning}
                </p>
              </div>
            ) : null}
            {candidate.ai_rejection_reason ? (
              <div>
                <p className="text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
                  Rejection reason
                </p>
                <p className="mt-1.5 text-xs capitalize text-[var(--hermes-danger)]">
                  {candidate.ai_rejection_reason.replaceAll("_", " ")}
                </p>
              </div>
            ) : null}
            {(truckName !== null || candidate.score_breakdown) ? (
              <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
                {truckName !== null ? (
                  <div>
                    <dt className="text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
                      Truck type
                    </dt>
                    <dd className="mt-1 text-xs capitalize text-[var(--hermes-text)]">{truckName}</dd>
                  </div>
                ) : null}
                {candidate.score_breakdown
                  ? Object.entries(candidate.score_breakdown).map(([key, value]) => (
                      <div key={key}>
                        <dt className="text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
                          {key.replaceAll("_", " ")}
                        </dt>
                        <dd className="mt-1 text-xs text-[var(--hermes-text)]">{value}</dd>
                      </div>
                    ))
                  : null}
              </dl>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── CandidateCard ─────────────────────────────────────────────────────────────

function CandidateCard({
  candidate,
  isBusy,
  onSelect,
  onClearSelection,
  emphasis,
  currency,
  truckName,
}: {
  candidate: CarrierCandidate;
  isBusy: boolean;
  onSelect: (tripId: string) => void;
  onClearSelection?: () => void;
  emphasis: "selected" | "candidate";
  currency: string;
  truckName: string | null;
}) {
  const canSelect = candidate.proposal_status === "candidate";
  const cardTone = {
    selected: "border-amber-400/30 bg-amber-400/[0.05]",
    candidate: "border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]",
  }[emphasis];
  const marginTone = !candidate.profit_margin
    ? "text-[var(--hermes-muted)]"
    : candidate.profit_margin.startsWith("-")
      ? "text-[var(--hermes-danger)]"
      : "text-[var(--hermes-success)]";

  return (
    <article className={`rounded-xl border p-5 transition ${cardTone}`}>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(17rem,0.95fr)_auto] xl:items-center">

        {/* Identity */}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold text-[var(--hermes-text)]">
              {candidate.company_name}
            </h2>
            {candidate.is_selected ? (
              <span className="rounded-full border border-emerald-400/30 px-2.5 py-0.5 text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-emerald-400/80">
                Selected
              </span>
            ) : null}
          </div>
          <p className="mt-1.5 font-mono text-xs text-[var(--hermes-muted)]">
            {candidate.trip_id.slice(0, 8)}
          </p>
        </div>

        {/* Carrier metrics */}
        <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-[var(--hermes-muted)]">Reliability</dt>
            <dd className="mt-0.5 text-[var(--hermes-text)]">
              {formatValue(candidate.reliability_rating)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--hermes-muted)]">Docs</dt>
            <dd className="mt-0.5 text-[var(--hermes-text)]">
              {formatValue(candidate.documentation_valid)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--hermes-muted)]">ADR</dt>
            <dd className="mt-0.5 text-[var(--hermes-text)]">
              {formatValue(candidate.adr_capable)}
            </dd>
          </div>
        </dl>

        {/* Pricing + action */}
        <div className="grid gap-4 xl:grid-cols-[minmax(14rem,1fr)_auto] xl:items-center">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm xl:min-w-[14rem]">
            <div>
              <dt className="text-xs text-[var(--hermes-muted)]">Bid price</dt>
              <dd className="mt-0.5 text-[var(--hermes-text)]">
                {formatMoney(candidate.carrier_price, currency)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--hermes-muted)]">Margin</dt>
              <dd className={`mt-0.5 font-medium ${marginTone}`}>
                {formatMargin(candidate.profit_margin)}
              </dd>
            </div>
          </dl>

          <div className="flex flex-wrap items-center justify-start gap-2 xl:flex-nowrap xl:justify-end">
            {candidate.is_selected ? (
              <button
                className="hermes-primary-button px-4 py-2 text-sm disabled:opacity-50"
                disabled={isBusy}
                onClick={() => onClearSelection?.()}
                type="button"
              >
                Deselect
              </button>
            ) : canSelect ? (
              <button
                className="hermes-primary-button px-4 py-2 text-sm disabled:opacity-50"
                disabled={isBusy}
                onClick={() => onSelect(candidate.trip_id)}
                type="button"
              >
                Select
              </button>
            ) : (
              <span className="rounded-full border border-white/10 px-3 py-1 text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-[var(--hermes-muted)]">
                {candidate.proposal_status}
              </span>
            )}
          </div>
        </div>

      </div>

      {/* Sub-row: ranking score at-a-glance */}
      {candidate.ranking_score ? (
        <div className="mt-4 flex items-center gap-2.5 border-t border-white/[0.06] pt-3">
          <span className="rounded-full border border-[var(--hermes-data)]/25 bg-[var(--hermes-data-soft)] px-2.5 py-0.5 text-xs font-medium text-[var(--hermes-data)]">
            Score {candidate.ranking_score}
          </span>
          {candidate.score_breakdown ? (
            <span className="text-xs text-[var(--hermes-muted)]">
              Route {candidate.score_breakdown.route_match?.toFixed(0) ?? "—"}
              {" · "}
              Price {candidate.score_breakdown.price_competitiveness?.toFixed(0) ?? "—"}
              {" · "}
              Rel {candidate.score_breakdown.reliability?.toFixed(0) ?? "—"}
            </span>
          ) : null}
        </div>
      ) : null}

      {/* Expandable details */}
      <CandidateDetails candidate={candidate} truckName={truckName} />

    </article>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export function CarrierMatchPage() {
  const { orderId = "" } = useParams();
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const hasAutoTriggeredSearchRef = useRef(false);

  const snapshotQuery = useQuery({
    queryKey: ["orders", orderId, "carrier-candidates"],
    queryFn: () => getCarrierCandidates(orderId, getToken),
    enabled: orderId.length > 0,
    retry: false,
  });

  const isMissingSnapshot =
    snapshotQuery.isError &&
    snapshotQuery.error instanceof ApiError &&
    snapshotQuery.error.status === 404;

  const truckTypesQuery = useQuery({
    queryKey: ["truck-types"],
    queryFn: () => listTruckTypes(getToken),
    staleTime: Infinity,
  });

  const orderQuery = useQuery({
    queryKey: ["orders", orderId],
    queryFn: () => getOrder(orderId, getToken),
    enabled: isMissingSnapshot && orderId.length > 0,
    retry: false,
  });

  const truckTypes = Array.isArray(truckTypesQuery.data) ? truckTypesQuery.data : [];
  const truckNameById = new Map(truckTypes.map((t) => [t.id, t.name]));

  const searchMutation = useMutation({
    mutationFn: () => runCarrierSearch(orderId, getToken),
    onSuccess: (snapshot) => {
      queryClient.setQueryData(["orders", orderId, "carrier-candidates"], snapshot);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders", orderId, "carrier-candidates"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", orderId] }),
        queryClient.invalidateQueries({ queryKey: ["orders"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", "summary"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "status"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "orchestrator", "timeline"] }),
      ]);
    },
  });

  const selectMutation = useMutation({
    mutationFn: (tripId: string) => selectCarrier(orderId, getToken, { trip_id: tripId }),
    onSuccess: (snapshot) => {
      queryClient.setQueryData(["orders", orderId, "carrier-candidates"], snapshot);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders", orderId, "carrier-candidates"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", orderId] }),
        queryClient.invalidateQueries({ queryKey: ["orders"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", "summary"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "status"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "orchestrator", "timeline"] }),
      ]);
    },
  });

  const clearSelectionMutation = useMutation({
    mutationFn: () => selectCarrier(orderId, getToken, { trip_id: null }),
    onSuccess: (snapshot) => {
      queryClient.setQueryData(["orders", orderId, "carrier-candidates"], snapshot);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders", orderId, "carrier-candidates"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", orderId] }),
        queryClient.invalidateQueries({ queryKey: ["orders"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", "summary"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "status"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "orchestrator", "timeline"] }),
      ]);
    },
  });

  const isBusy =
    searchMutation.isPending || selectMutation.isPending || clearSelectionMutation.isPending;
  const snapshot = snapshotQuery.data;

  useEffect(() => {
    if (!isMissingSnapshot) {
      hasAutoTriggeredSearchRef.current = false;
      return;
    }

    if (orderQuery.data?.status !== "viability_confirmed") {
      return;
    }

    if (searchMutation.isPending || hasAutoTriggeredSearchRef.current) {
      return;
    }

    hasAutoTriggeredSearchRef.current = true;
    void searchMutation.mutateAsync();
  }, [
    isMissingSnapshot,
    orderQuery.data?.status,
    searchMutation,
    searchMutation.isPending,
  ]);

  if (snapshotQuery.isLoading) {
    return <WorkspaceLoader label="Loading carrier match" />;
  }

  if (snapshotQuery.isError && !isMissingSnapshot) {
    return <StateBlock tone="error" title="Failed to load carrier match" />;
  }

  if (searchMutation.isError && searchMutation.error instanceof ApiError && searchMutation.error.status === 409) {
    return (
      <section className="space-y-6">
        <PageHeader
          actions={(
            <Link
              className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 transition-colors duration-150 hover:border-white/20 hover:bg-white/[0.04]"
              to={`/orders/${orderId}`}
            >
              Back to order
            </Link>
          )}
          eyebrow="Carrier decision"
          title="Carrier match"
        />
        <StateBlock
          tone="error"
          title="Carrier search is not available yet"
          description={searchMutation.error.detail ?? String(searchMutation.error)}
        />
      </section>
    );
  }

  // No snapshot exists yet — prompt to run the search
  if (isMissingSnapshot) {
    const canRunSearch = orderQuery.data?.status === "viability_confirmed";

    return (
      <section className="space-y-6">
        <PageHeader
          actions={(
            <Link
              className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 transition-colors duration-150 hover:border-white/20 hover:bg-white/[0.04]"
              to={`/orders/${orderId}`}
            >
              Back to order
            </Link>
          )}
          eyebrow="Carrier decision"
          title="Carrier match"
        />
        <p className="text-sm text-[var(--hermes-muted)]">
          No carrier search has been run for this order yet.
        </p>
        {orderQuery.isLoading ? (
          <p className="text-sm text-[var(--hermes-muted)]">Checking whether carrier search is available…</p>
        ) : null}
        {searchMutation.isPending ? (
          <WorkspaceLoader label="Running carrier search" />
        ) : null}
        {searchMutation.isError ? (
          <StateBlock tone="error" title={String(searchMutation.error)} />
        ) : null}
        {!orderQuery.isLoading ? (
          canRunSearch ? (
            <>
              <p className="text-xs uppercase tracking-widest text-[var(--hermes-muted)]">
                Carrier search starts once the order is {formatOrderStatusLabel("viability_confirmed").toLowerCase()}.
              </p>
              <button
                className="hermes-primary-button px-5 py-2.5 text-sm disabled:opacity-50"
                disabled={isBusy}
                onClick={() => { void searchMutation.mutateAsync(); }}
                type="button"
              >
                {searchMutation.isPending ? "Searching…" : "Run carrier search again"}
              </button>
            </>
          ) : (
            <StateBlock
              tone="empty"
              title="Carrier search is not available yet"
              description={`Current order status: ${formatOrderStatusLabel(orderQuery.data?.status ?? "unknown")}. Complete intake review first.`}
            />
          )
        ) : null}
      </section>
    );
  }

  if (!snapshot) {
    return <WorkspaceLoader label="Loading carrier match" />;
  }

  const selectedCandidates = snapshot.candidates.filter((c) => c.is_selected);
  const candidatePool = snapshot.candidates.filter(
    (c) => c.proposal_status === "candidate" && !c.is_selected,
  );

  return (
    <section className="space-y-6">
      <PageHeader
        actions={
          <Link
            className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 transition-colors duration-150 hover:border-white/20 hover:bg-white/[0.04]"
            to={`/orders/${orderId}`}
          >
            Back to order
          </Link>
        }
        eyebrow="Carrier decision"
        title="Carrier match"
      />

      {/* ── Order context + search action ─────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-[var(--hermes-border)] pb-5">
        <div>
          <p className="text-base font-semibold text-[var(--hermes-text)]">
            {snapshot.load_order.origin_text ?? "—"}
            <span className="mx-2 text-[var(--hermes-muted)]">→</span>
            {snapshot.load_order.destination_text ?? "—"}
          </p>
          <p className="mt-1 text-xs text-[var(--hermes-muted)]">
            {formatValue(snapshot.load_order.weight_kg)} kg
            <span className="mx-2 opacity-40">·</span>
            Customer price: {formatMoney(snapshot.load_order.customer_price, snapshot.load_order.currency)}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <span className="flex items-center gap-1.5 text-xs text-[var(--hermes-muted)]">
            <span
              className={`h-1.5 w-1.5 rounded-full ${isBusy ? "bg-orange-400" : "bg-emerald-400/70"}`}
            />
            {isBusy ? "Scanning…" : "Snapshot ready"}
          </span>
          <StatusBadge status={snapshot.load_order.status} />
          <button
            className="hermes-secondary-button px-4 py-2 text-sm disabled:opacity-50"
            disabled={isBusy}
            onClick={() => { void searchMutation.mutateAsync(); }}
            type="button"
          >
            {searchMutation.isPending ? "Searching…" : "Run carrier search"}
          </button>
        </div>
      </div>

      {/* ── Selected carrier ──────────────────────────────────────────────── */}
      <section className="space-y-3">
        <h2 className="text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
          Selected carrier
        </h2>
        {selectedCandidates.length > 0 ? (
          <div className="space-y-3">
            {selectedCandidates.map((candidate) => (
              <CandidateCard
                candidate={candidate}
                currency={snapshot.load_order.currency}
                emphasis="selected"
                isBusy={isBusy}
                key={candidate.trip_id}
                onClearSelection={() => { void clearSelectionMutation.mutateAsync(); }}
                onSelect={(tripId) => { void selectMutation.mutateAsync(tripId); }}
                truckName={candidate.truck_type_id !== null ? (truckNameById.get(candidate.truck_type_id) ?? null) : null}
              />
            ))}
          </div>
        ) : (
          <p className="text-sm text-[var(--hermes-muted)]">
            No carrier selected — pick one from the list below.
          </p>
        )}
      </section>

      {/* ── Candidate comparison ──────────────────────────────────────────── */}
      <section className="space-y-3">
        <h2 className="text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
          Candidate comparison
        </h2>
        {candidatePool.length > 0 ? (
          <div className="space-y-3">
            {candidatePool.map((candidate) => (
              <CandidateCard
                candidate={candidate}
                currency={snapshot.load_order.currency}
                emphasis="candidate"
                isBusy={isBusy}
                key={candidate.trip_id}
                onSelect={(tripId) => { void selectMutation.mutateAsync(tripId); }}
                truckName={candidate.truck_type_id !== null ? (truckNameById.get(candidate.truck_type_id) ?? null) : null}
              />
            ))}
          </div>
        ) : (
          <StateBlock tone="empty" title="No candidate offers available" />
        )}
      </section>

    </section>
  );
}
