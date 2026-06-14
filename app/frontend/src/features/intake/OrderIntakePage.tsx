import { useAuth } from "@clerk/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  confirmViability,
  geocodeDistance,
  getHumanValidationContext,
  type HumanValidationContext,
  updateHumanValidation,
} from "./api";
import { PageHeader } from "../../app/ui/PageHeader";
import { StateBlock } from "../../app/ui/StateBlock";
import { StatusBadge } from "../../app/ui/StatusBadge";
import { WorkspaceLoader } from "../../app/ui/WorkspaceLoader";
import { ApiError } from "../../lib/apiClient";
import {
  handleDateTimeLocalKeyDown,
  openDateTimeLocalPicker,
  preventDateTimeLocalPaste,
  toDateTimeLocalApiValue,
  toDateTimeLocalInputValue,
} from "../../lib/datetimeLocal";

// ─── Types ─────────────────────────────────────────────────────────────────────

type ReviewFormState = {
  customer_name: string;
  destination_text: string;
  origin_text: string;
  origin_load_date: string;
  destination_unload_date: string;
  distance_km: string;
  cargo_description: string;
  weight_kg: string;
  truck_type_id: string;
  customer_price: string;
  currency: string;
  adr_required: boolean;
};

const MINIMUM_REQUIRED_FIELDS = [
  "customer_name",
  "origin_text",
  "destination_text",
  "origin_load_date",
  "cargo_description",
] as const;

const SEARCH_REQUIRED_FIELDS = [
  "customer_price",
  "distance_km",
] as const;

// ─── Helpers ───────────────────────────────────────────────────────────────────

function buildFormState(context: HumanValidationContext): ReviewFormState {
  return {
    customer_name: context.load_order.customer_name ?? "",
    destination_text: context.load_order.destination_text ?? "",
    origin_text: context.load_order.origin_text ?? "",
    origin_load_date: toDateTimeLocalInputValue(context.load_order.origin_load_date),
    destination_unload_date: toDateTimeLocalInputValue(context.load_order.destination_unload_date),
    distance_km: context.load_order.distance_km ?? "",
    cargo_description: context.load_order.cargo_description ?? "",
    weight_kg: context.load_order.weight_kg ?? "",
    truck_type_id: context.load_order.truck_type_id ? String(context.load_order.truck_type_id) : "",
    customer_price: context.load_order.customer_price ?? "",
    currency: context.load_order.currency ?? "",
    adr_required: context.load_order.adr_required,
  };
}

function buildReviewUpdatePayload(
  formState: ReviewFormState,
  reviewableFields: string[],
) {
  return {
    ...(reviewableFields.includes("customer_name") && formState.customer_name
      ? { customer_name: formState.customer_name } : {}),
    ...(reviewableFields.includes("destination_text") && formState.destination_text
      ? { destination_text: formState.destination_text } : {}),
    ...(reviewableFields.includes("origin_text") && formState.origin_text
      ? { origin_text: formState.origin_text } : {}),
    ...(reviewableFields.includes("origin_load_date") && formState.origin_load_date
      ? { origin_load_date: toDateTimeLocalApiValue(formState.origin_load_date) ?? undefined } : {}),
    ...(reviewableFields.includes("destination_unload_date") && formState.destination_unload_date
      ? { destination_unload_date: toDateTimeLocalApiValue(formState.destination_unload_date) ?? undefined } : {}),
    ...(reviewableFields.includes("distance_km") && formState.distance_km
      ? { distance_km: formState.distance_km } : {}),
    ...(reviewableFields.includes("cargo_description") && formState.cargo_description
      ? { cargo_description: formState.cargo_description } : {}),
    ...(reviewableFields.includes("weight_kg") && formState.weight_kg
      ? { weight_kg: formState.weight_kg } : {}),
    ...(reviewableFields.includes("truck_type_id") && formState.truck_type_id
      ? { truck_type_id: Number(formState.truck_type_id) } : {}),
    ...(reviewableFields.includes("customer_price") && formState.customer_price
      ? { customer_price: formState.customer_price } : {}),
    ...(reviewableFields.includes("currency") && formState.currency
      ? { currency: formState.currency } : {}),
    ...(reviewableFields.includes("adr_required")
      ? { adr_required: formState.adr_required } : {}),
  };
}

function formatMutationError(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.detail?.startsWith("Human validation not allowed for status:")) {
      return "Review is locked for this order status.";
    }
    return error.detail ?? fallback;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return fallback;
}

// ─── Sub-components ────────────────────────────────────────────────────────────

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-5 text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
      {children}
    </h2>
  );
}

/** Asterisk badge — marks fields that came from the AI extraction */
function SparkleBadge() {
  return (
    <span aria-label="AI-extracted field" className="text-[0.6rem] font-semibold text-[var(--hermes-data)]">
      *
    </span>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export function OrderIntakePage() {
  const { orderId = "" } = useParams();
  const navigate = useNavigate();
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const [formState, setFormState] = useState<ReviewFormState | null>(null);
  const [isDirty, setIsDirty] = useState(false);

  const contextQuery = useQuery({
    queryKey: ["orders", orderId, "human-validation"],
    queryFn: () => getHumanValidationContext(orderId, getToken),
    enabled: orderId.length > 0,
  });

  useEffect(() => {
    if (contextQuery.data && !isDirty) {
      setFormState(buildFormState(contextQuery.data));
    }
  }, [contextQuery.data, isDirty]);

  const reviewMutation = useMutation({
    mutationFn: async () => {
      if (!formState) throw new Error("Review form is not ready");
      if (!["pending_ingestion", "viability_pending"].includes(contextQuery.data?.load_order.status ?? "")) {
        throw new Error("Review is locked for this order status.");
      }
      return updateHumanValidation(
        orderId,
        getToken,
        buildReviewUpdatePayload(formState, contextQuery.data?.reviewable_fields ?? []),
      );
    },
    onSuccess: () => {
      setIsDirty(false);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders", orderId, "human-validation"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", orderId] }),
        queryClient.invalidateQueries({ queryKey: ["orders"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", "summary"] }),
      ]);
    },
  });

  const confirmMutation = useMutation({
    mutationFn: async () => {
      if (isDirty && formState) {
        await updateHumanValidation(
          orderId,
          getToken,
          buildReviewUpdatePayload(formState, contextQuery.data?.reviewable_fields ?? []),
        );
      }
      return confirmViability(orderId, getToken, {});
    },
    onSuccess: () => {
      setIsDirty(false);
      navigate(`/orders/${orderId}/carrier-match`);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders", orderId, "human-validation"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", orderId] }),
        queryClient.invalidateQueries({ queryKey: ["orders"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", "summary"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "status"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "orchestrator", "timeline"] }),
      ]);
    },
  });

  const geocodeMutation = useMutation({
    mutationFn: async () => {
      return geocodeDistance(formState?.origin_text ?? "", formState?.destination_text ?? "", getToken);
    },
    onSuccess: (result) => {
      if (formState) {
        setIsDirty(true);
        setFormState({ ...formState, distance_km: String(result.distance_km) });
      }
    },
  });

  const isBusy = reviewMutation.isPending || confirmMutation.isPending;

  if (contextQuery.isLoading) {
    return <WorkspaceLoader label="Loading intake review" />;
  }
  if (contextQuery.isError) {
    return <StateBlock tone="error" title="Failed to load intake review" />;
  }
  if (!contextQuery.data) {
    return <StateBlock tone="error" title="Failed to load intake review" />;
  }
  if (!formState) {
    return <WorkspaceLoader label="Loading intake review" />;
  }

  // All guards passed — safe to use these without null checks below
  const context = contextQuery.data;
  const currentFormState = formState;
  const extractedPayload = context.latest_ingestion_run.extracted_payload ?? {};
  const visibleMissingFields = new Set(
    Object.keys(context.missing_fields).filter((fieldName) => {
      if (!(fieldName in currentFormState)) {
        return true;
      }
      const value = currentFormState[fieldName as keyof ReviewFormState];
      return typeof value === "string" ? value.trim().length === 0 : false;
    }),
  );
  for (const fieldName of SEARCH_REQUIRED_FIELDS) {
    if (currentFormState[fieldName].trim().length === 0) {
      visibleMissingFields.add(fieldName);
    }
  }
  const missingFieldEntries = Array.from(visibleMissingFields, (fieldName) => [fieldName, "not_found"] as const);
  const blockedFieldEntries = Object.entries(context.blocked_missing_fields);
  const hasAllViabilityFields = MINIMUM_REQUIRED_FIELDS.every((fieldName) => currentFormState[fieldName].trim().length > 0);
  const hasAllSearchFields = SEARCH_REQUIRED_FIELDS.every((fieldName) => currentFormState[fieldName].trim().length > 0);
  const canSaveReview = !isBusy
    && ["pending_ingestion", "viability_pending"].includes(context.load_order.status);
  const canConfirmViability = !isBusy
    && ["pending_ingestion", "viability_pending"].includes(context.load_order.status)
    && hasAllViabilityFields
    && hasAllSearchFields;
  const confirmHelperText = !["pending_ingestion", "viability_pending"].includes(context.load_order.status)
    ? "Viability is already confirmed for this order."
    : hasAllViabilityFields && !hasAllSearchFields
      ? "Fill carrier search fields to enable"
      : "Fill missing fields to enable";
  const currentStatus = context.load_order.status === "pending_ingestion" && hasAllViabilityFields
    ? "viability_pending"
    : context.load_order.status;

  // Field helpers
  const isDisabled = (f: keyof ReviewFormState) =>
    !context.reviewable_fields.includes(f) || isBusy;
  const isExtracted = (f: keyof ReviewFormState) => extractedPayload[f] !== undefined;
  const labelCls = (f: keyof ReviewFormState) => {
    if (f in context.blocked_missing_fields) return "text-[var(--hermes-danger)]";
    if (visibleMissingFields.has(f)) return "text-amber-400/80";
    return "text-[var(--hermes-muted)]";
  };

  // Input state class — transparent bg for filled fields, amber for missing, rose for blocked
  const inputCls = (f: keyof ReviewFormState) => {
    if (f in context.blocked_missing_fields) return "hermes-review-input is-blocked";
    if (visibleMissingFields.has(f)) return "hermes-review-input is-missing";
    return "hermes-review-input";
  };

  const onChangeText =
    (f: Exclude<keyof ReviewFormState, "adr_required">) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setIsDirty(true);
      setFormState((prev) => (prev ? { ...prev, [f]: e.target.value } : prev));
    };

  const onChangeNumeric =
    (f: "customer_price" | "distance_km" | "weight_kg") =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const filtered = e.target.value.replace(/[^0-9.]/g, "").replace(/(\..*)\./g, "$1");
      setIsDirty(true);
      setFormState((prev) => (prev ? { ...prev, [f]: filtered } : prev));
    };

  function rangeWarning(field: "customer_price" | "distance_km" | "weight_kg"): string | null {
    const raw = currentFormState[field].trim();
    if (!raw) return null;
    const value = parseFloat(raw);
    if (isNaN(value)) return null;
    switch (field) {
      case "customer_price":
        if (value < 50) return "Price seems unusually low";
        if (value > 50000) return "Price seems unusually high";
        break;
      case "distance_km":
        if (value < 1) return "Distance seems unusually short";
        if (value > 5000) return "Distance seems unusually long";
        break;
      case "weight_kg":
        if (value < 1) return "Weight seems unusually low";
        if (value > 40000) return "Weight seems unusually high";
        break;
    }
    return null;
  }

  return (
    <section className="space-y-6">
      <PageHeader
        actions={
          <Link
            className="rounded-lg border border-white/10 px-4 py-2 text-sm text-[var(--hermes-text)] transition-colors hover:border-white/20 hover:bg-white/[0.04]"
            to={`/orders/${orderId}`}
          >
            Back to order
          </Link>
        }
        eyebrow="Human review"
        title="Intake & viability"
      />

      {/* ── Top strip: Source request | Agent summary ────────────────────────── */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">

        {/* Source request */}
        <div className="flex max-h-56 flex-col rounded-xl border border-[var(--hermes-border)]">
          <div className="flex shrink-0 items-center justify-between px-5 py-3.5">
            <div className="flex items-center gap-3">
              <span className="text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
                Source request
              </span>
              {context.latest_ingestion_run.route ? (
                <span className="text-xs text-[var(--hermes-muted)]">
                  {context.latest_ingestion_run.route}
                </span>
              ) : null}
            </div>
            <span className="text-[0.65rem] uppercase tracking-widest text-[var(--hermes-muted)]">
              {context.latest_ingestion_run.status}
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto border-t border-[var(--hermes-border)] px-5 py-4">
            <pre className="whitespace-pre-wrap font-mono text-xs leading-6 text-[var(--hermes-muted)]">
              {context.latest_ingestion_run.raw_text}
            </pre>
          </div>
        </div>

        {/* Agent summary */}
        <div className="flex max-h-56 flex-col rounded-xl border border-[var(--hermes-border)]">
          <div className="shrink-0 px-5 py-3.5">
            <span className="text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
              Agent summary
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto border-t border-[var(--hermes-border)] px-5 py-4 space-y-3">

            <div className="grid grid-cols-3 gap-3">
              <div>
                <p className="text-xs text-[var(--hermes-muted)]">Extracted</p>
                <p className="mt-0.5 text-sm font-medium text-[var(--hermes-text)]">
                  {Object.keys(extractedPayload).length}
                </p>
              </div>
              <div>
                <p className="text-xs text-[var(--hermes-muted)]">Missing</p>
                <p className={`mt-0.5 text-sm font-medium ${missingFieldEntries.length > 0 ? "text-amber-400/80" : "text-[var(--hermes-text)]"}`}>
                  {missingFieldEntries.length}
                </p>
              </div>
              <div>
                <p className="text-xs text-[var(--hermes-muted)]">Reviewable</p>
                <p className="mt-0.5 text-sm font-medium text-[var(--hermes-text)]">
                  {context.reviewable_fields.length}
                </p>
              </div>
            </div>

            <div className="space-y-1.5">
              {context.latest_ingestion_run.execution_path ? (
                <div className="flex items-baseline justify-between gap-2">
                  <span className="shrink-0 text-xs text-[var(--hermes-muted)]">Path</span>
                  <span className="truncate text-right text-xs text-[var(--hermes-text)]">
                    {context.latest_ingestion_run.execution_path}
                  </span>
                </div>
              ) : null}
              {context.latest_ingestion_run.provider ? (
                <div className="flex items-baseline justify-between gap-2">
                  <span className="shrink-0 text-xs text-[var(--hermes-muted)]">Provider</span>
                  <span className="truncate text-right text-xs text-[var(--hermes-text)]">
                    {context.latest_ingestion_run.provider}
                  </span>
                </div>
              ) : null}
              {context.latest_ingestion_run.model_name ? (
                <div className="flex items-baseline justify-between gap-2">
                  <span className="shrink-0 text-xs text-[var(--hermes-muted)]">Model</span>
                  <span className="truncate text-right text-xs text-[var(--hermes-text)]">
                    {context.latest_ingestion_run.model_name}
                  </span>
                </div>
              ) : null}
            </div>

            {context.latest_ingestion_run.trace_steps &&
            context.latest_ingestion_run.trace_steps.length > 0 ? (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {context.latest_ingestion_run.trace_steps.map((step, index) => (
                  <span
                    key={index}
                    className="rounded border border-white/8 bg-white/[0.03] px-2 py-0.5 text-[0.65rem]"
                  >
                    <span className="text-[var(--hermes-agent)]">{String(step.node ?? "")}</span>
                    {step.outcome ? (
                      <span className="ml-1 text-[var(--hermes-muted)]">{String(step.outcome)}</span>
                    ) : null}
                  </span>
                ))}
              </div>
            ) : null}

          </div>
        </div>

      </div>

      {/* ── Main: form fields + decision panel ───────────────────────────────── */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_300px] lg:items-start">

        {/* Left: review fields */}
        <div className="min-w-0">

          <form onSubmit={(e) => e.preventDefault()}>
            <p className="mb-6 text-xs text-[var(--hermes-muted)]">
              Fields marked <span className="font-semibold text-[var(--hermes-data)]">*</span> were
              extracted by the ingestion agent — verify before confirming.
            </p>

            <div className="divide-y divide-[var(--hermes-border)]">

              {/* Commercial */}
              <div className="py-7">
                <SectionHeading>Commercial</SectionHeading>
                <div className="grid gap-x-6 gap-y-4 md:grid-cols-2">

                  <label className="block">
                    <span className={`mb-1.5 flex items-center gap-1.5 text-xs ${labelCls("customer_name")}`}>
                      Customer name {isExtracted("customer_name") ? <SparkleBadge /> : null}
                    </span>
                    <input
                      className={inputCls("customer_name")}
                      disabled={isDisabled("customer_name")}
                      onChange={onChangeText("customer_name")}
                      type="text"
                      value={formState.customer_name}
                    />
                  </label>

                  <label className="block">
                    <span className={`mb-1.5 flex items-center gap-1.5 text-xs ${labelCls("customer_price")}`}>
                      Customer price {isExtracted("customer_price") ? <SparkleBadge /> : null}
                    </span>
                    <input
                      className={inputCls("customer_price")}
                      disabled={isDisabled("customer_price")}
                      onChange={onChangeNumeric("customer_price")}
                      type="text"
                      value={formState.customer_price}
                    />
                    {rangeWarning("customer_price") ? (
                      <p className="mt-1 text-xs text-amber-400/70">{rangeWarning("customer_price")}</p>
                    ) : null}
                  </label>

                  <label className="block">
                    <span className={`mb-1.5 flex items-center gap-1.5 text-xs ${labelCls("currency")}`}>
                      Currency {isExtracted("currency") ? <SparkleBadge /> : null}
                    </span>
                    <input
                      className={inputCls("currency")}
                      disabled={isDisabled("currency")}
                      onChange={onChangeText("currency")}
                      type="text"
                      value={formState.currency}
                    />
                  </label>

                </div>
              </div>

              {/* Route */}
              <div className="py-7">
                <SectionHeading>Route</SectionHeading>
                <div className="grid gap-x-6 gap-y-4 md:grid-cols-2">

                  <label className="block">
                    <span className={`mb-1.5 flex items-center gap-1.5 text-xs ${labelCls("origin_text")}`}>
                      Origin {isExtracted("origin_text") ? <SparkleBadge /> : null}
                    </span>
                    <input
                      className={inputCls("origin_text")}
                      disabled={isDisabled("origin_text")}
                      onChange={onChangeText("origin_text")}
                      type="text"
                      value={formState.origin_text}
                    />
                  </label>

                  <label className="block">
                    <span className={`mb-1.5 flex items-center gap-1.5 text-xs ${labelCls("destination_text")}`}>
                      Destination {isExtracted("destination_text") ? <SparkleBadge /> : null}
                    </span>
                    <input
                      className={inputCls("destination_text")}
                      disabled={isDisabled("destination_text")}
                      onChange={onChangeText("destination_text")}
                      type="text"
                      value={formState.destination_text}
                    />
                  </label>

                  <label className="block">
                    <span className={`mb-1.5 flex items-center gap-1.5 text-xs ${labelCls("distance_km")}`}>
                      Distance (km) {isExtracted("distance_km") ? <SparkleBadge /> : null}
                    </span>
                    <div className="flex gap-2">
                      <input
                        className={inputCls("distance_km")}
                        disabled={isDisabled("distance_km")}
                        onChange={onChangeNumeric("distance_km")}
                        type="text"
                        value={formState.distance_km}
                      />
                      <button
                        className="shrink-0 rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-400 transition-colors hover:border-white/20 hover:bg-white/[0.06] disabled:opacity-30"
                        disabled={!formState.origin_text.trim() || !formState.destination_text.trim() || geocodeMutation.isPending}
                        onClick={() => { void geocodeMutation.mutateAsync(); }}
                        title="Calculate road distance between origin and destination"
                        type="button"
                      >
                        {geocodeMutation.isPending ? "..." : "Calculate"}
                      </button>
                    </div>
                    {geocodeMutation.isError ? (
                      <p className="mt-1 text-xs text-[var(--hermes-danger)]">Distance calculation failed</p>
                    ) : rangeWarning("distance_km") ? (
                      <p className="mt-1 text-xs text-amber-400/70">{rangeWarning("distance_km")}</p>
                    ) : null}
                  </label>

                </div>
              </div>

              {/* Schedule */}
              <div className="py-7">
                <SectionHeading>Schedule</SectionHeading>
                <div className="grid gap-x-6 gap-y-4 md:grid-cols-2">

                  <label className="block">
                    <span className={`mb-1.5 flex items-center gap-1.5 text-xs ${labelCls("origin_load_date")}`}>
                      Origin load date {isExtracted("origin_load_date") ? <SparkleBadge /> : null}
                    </span>
                    <input
                      className={inputCls("origin_load_date")}
                      disabled={isDisabled("origin_load_date")}
                      inputMode="none"
                      onClick={openDateTimeLocalPicker}
                      onChange={onChangeText("origin_load_date")}
                      onDrop={preventDateTimeLocalPaste}
                      onKeyDown={handleDateTimeLocalKeyDown}
                      onPaste={preventDateTimeLocalPaste}
                      step={60}
                      type="datetime-local"
                      value={formState.origin_load_date}
                    />
                  </label>

                  <label className="block">
                    <span className={`mb-1.5 flex items-center gap-1.5 text-xs ${labelCls("destination_unload_date")}`}>
                      Destination unload date{" "}
                      {isExtracted("destination_unload_date") ? <SparkleBadge /> : null}
                    </span>
                    <input
                      className={inputCls("destination_unload_date")}
                      disabled={isDisabled("destination_unload_date")}
                      inputMode="none"
                      onClick={openDateTimeLocalPicker}
                      onChange={onChangeText("destination_unload_date")}
                      onDrop={preventDateTimeLocalPaste}
                      onKeyDown={handleDateTimeLocalKeyDown}
                      onPaste={preventDateTimeLocalPaste}
                      step={60}
                      type="datetime-local"
                      value={formState.destination_unload_date}
                    />
                  </label>

                </div>
              </div>

              {/* Cargo */}
              <div className="py-7">
                <SectionHeading>Cargo</SectionHeading>
                <div className="grid gap-x-6 gap-y-4 md:grid-cols-2">

                  <label className="block md:col-span-2">
                    <span className={`mb-1.5 flex items-center gap-1.5 text-xs ${labelCls("cargo_description")}`}>
                      Cargo description {isExtracted("cargo_description") ? <SparkleBadge /> : null}
                    </span>
                    <input
                      className={inputCls("cargo_description")}
                      disabled={isDisabled("cargo_description")}
                      onChange={onChangeText("cargo_description")}
                      type="text"
                      value={formState.cargo_description}
                    />
                  </label>

                  <label className="block">
                    <span className={`mb-1.5 flex items-center gap-1.5 text-xs ${labelCls("weight_kg")}`}>
                      Weight (kg) {isExtracted("weight_kg") ? <SparkleBadge /> : null}
                    </span>
                    <input
                      className={inputCls("weight_kg")}
                      disabled={isDisabled("weight_kg")}
                      onChange={onChangeNumeric("weight_kg")}
                      type="text"
                      value={formState.weight_kg}
                    />
                    {rangeWarning("weight_kg") ? (
                      <p className="mt-1 text-xs text-amber-400/70">{rangeWarning("weight_kg")}</p>
                    ) : null}
                  </label>

                  <label className="block">
                    <span className={`mb-1.5 flex items-center gap-1.5 text-xs ${labelCls("truck_type_id")}`}>
                      Truck type {isExtracted("truck_type_id") ? <SparkleBadge /> : null}
                    </span>
                    <select
                      className={inputCls("truck_type_id")}
                      disabled={isDisabled("truck_type_id")}
                      onChange={(e) => {
                        setIsDirty(true);
                        setFormState({ ...formState, truck_type_id: e.target.value });
                      }}
                      value={formState.truck_type_id}
                    >
                      <option value="">Select truck type</option>
                      <option value="1">tautliner</option>
                      <option value="2">reefer</option>
                      <option value="3">mega</option>
                    </select>
                  </label>

                  <label className="flex cursor-pointer items-center gap-3 md:col-span-2">
                    <input
                      checked={formState.adr_required}
                      className="h-4 w-4 accent-[var(--hermes-accent)]"
                      disabled={isDisabled("adr_required")}
                      onChange={(e) => {
                        setIsDirty(true);
                        setFormState({ ...formState, adr_required: e.target.checked });
                      }}
                      type="checkbox"
                    />
                    <span className={`flex items-center gap-1.5 text-sm ${labelCls("adr_required")}`}>
                      ADR required {isExtracted("adr_required") ? <SparkleBadge /> : null}
                    </span>
                  </label>

                </div>
              </div>

            </div>
          </form>

        </div>

        {/* Right: decision panel */}
        <div className="space-y-4 rounded-xl border border-[var(--hermes-border)] bg-[var(--hermes-panel)] p-5">

          {/* Status + order ID */}
          <div className="flex items-center justify-between">
            <StatusBadge status={currentStatus} />
            <span className="font-mono text-xs text-[var(--hermes-muted)]">
              {orderId.slice(0, 8)}
            </span>
          </div>

          {/* Field health */}
          <div className="space-y-3">
            {missingFieldEntries.length > 0 ? (
              <div>
                <p className="mb-1.5 text-xs font-medium text-amber-400/80">
                  {missingFieldEntries.length} missing
                </p>
                <ul className="space-y-1">
                  {missingFieldEntries.map(([f]) => (
                    <li key={f} className="text-xs text-amber-400/60">
                      · {f.replaceAll("_", " ")}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-xs text-[var(--hermes-success)]">All fields present</p>
            )}

            {blockedFieldEntries.length > 0 ? (
              <div>
                <p className="mb-1.5 text-xs font-medium text-[var(--hermes-danger)]">
                  {blockedFieldEntries.length} blocked
                </p>
                <ul className="space-y-1">
                  {blockedFieldEntries.map(([f]) => (
                    <li key={f} className="text-xs text-rose-400/60">
                      · {f.replaceAll("_", " ")}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>

          {/* Actions */}
          <div className="space-y-2 border-t border-[var(--hermes-border)] pt-4">
            <button
              className="hermes-primary-button w-full px-4 py-2.5 text-sm disabled:opacity-50"
              disabled={!canConfirmViability}
              onClick={() => { void confirmMutation.mutateAsync(); }}
              type="button"
            >
              {confirmMutation.isPending ? "Confirming..." : "Confirm Viability & Search"}
            </button>

            {!canConfirmViability ? (
              <p className="text-center text-xs text-[var(--hermes-muted)]">
                {confirmHelperText}
              </p>
            ) : null}

            <button
              className="hermes-secondary-button w-full px-4 py-2 text-sm disabled:opacity-50"
              disabled={!canSaveReview}
              onClick={() => { void reviewMutation.mutateAsync(); }}
              type="button"
            >
              {reviewMutation.isPending ? "Saving..." : "Save review"}
            </button>

            {!canSaveReview ? (
              <p className="text-center text-xs text-[var(--hermes-muted)]">
                Review is locked for this order status.
              </p>
            ) : null}
          </div>

          {/* Errors */}
          {reviewMutation.isError ? (
            <p className="text-xs text-[var(--hermes-danger)]">
              {formatMutationError(reviewMutation.error, "Failed to save review.")}
            </p>
          ) : null}
          {confirmMutation.isError ? (
            <p className="text-xs text-[var(--hermes-danger)]">
              {formatMutationError(confirmMutation.error, "Failed to confirm viability.")}
            </p>
          ) : null}

        </div>

      </div>
    </section>
  );
}
