import { useAuth } from "@clerk/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router-dom";

import { PageHeader } from "../../app/ui/PageHeader";
import { StatusBadge } from "../../app/ui/StatusBadge";
import { SurfacePanel } from "../../app/ui/SurfacePanel";
import { WorkspaceLoader } from "../../app/ui/WorkspaceLoader";
import { ApiError } from "../../lib/apiClient";
import {
  handleDateTimeLocalKeyDown,
  openDateTimeLocalPicker,
  preventDateTimeLocalPaste,
  toDateTimeLocalApiValue,
  toDateTimeLocalInputValue,
} from "../../lib/datetimeLocal";
import {
  createOrder,
  delegateOrderAction,
  getOrder,
  listTruckTypes,
  type LoadOrder,
  type LoadOrderMutationPayload,
  updateOrder,
} from "./api";

type OrderFormPageProps = {
  mode: "create" | "edit";
};

type OrderFormValues = {
  customer_name: string;
  origin_text: string;
  origin_load_date: string;
  destination_text: string;
  destination_unload_date: string;
  distance_km: string;
  cargo_description: string;
  weight_kg: string;
  truck_type_id: string;
  adr_required: boolean;
  customer_price: string;
  currency: string;
};

const EMPTY_VALUES: OrderFormValues = {
  customer_name: "",
  origin_text: "",
  origin_load_date: "",
  destination_text: "",
  destination_unload_date: "",
  distance_km: "",
  cargo_description: "",
  weight_kg: "",
  truck_type_id: "",
  adr_required: false,
  customer_price: "",
  currency: "EUR",
};

function normalizeValue(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function toFormValues(order: LoadOrder): OrderFormValues {
  return {
    customer_name: order.customer_name ?? "",
    origin_text: order.origin_text ?? "",
    origin_load_date: toDateTimeLocalInputValue(order.origin_load_date),
    destination_text: order.destination_text ?? "",
    destination_unload_date: toDateTimeLocalInputValue(order.destination_unload_date),
    distance_km: order.distance_km ?? "",
    cargo_description: order.cargo_description ?? "",
    weight_kg: order.weight_kg ?? "",
    truck_type_id: order.truck_type_id ? String(order.truck_type_id) : "",
    adr_required: order.adr_required,
    customer_price: order.customer_price ?? "",
    currency: order.currency ?? "EUR",
  };
}

function toMutationPayload(values: OrderFormValues): LoadOrderMutationPayload {
  return {
    customer_name: normalizeValue(values.customer_name),
    origin_text: normalizeValue(values.origin_text),
    origin_load_date: toDateTimeLocalApiValue(values.origin_load_date),
    destination_text: normalizeValue(values.destination_text),
    destination_unload_date: toDateTimeLocalApiValue(values.destination_unload_date),
    distance_km: normalizeValue(values.distance_km),
    cargo_description: normalizeValue(values.cargo_description),
    weight_kg: normalizeValue(values.weight_kg),
    truck_type_id: values.truck_type_id ? Number(values.truck_type_id) : null,
    adr_required: values.adr_required,
    customer_price: normalizeValue(values.customer_price),
    currency: normalizeValue(values.currency)?.toUpperCase() ?? null,
  };
}

function formatExtractError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.detail === "Load order ingestion failed") {
      return "Draft extraction failed. Try again or continue by filling the form manually.";
    }
    return error.detail ?? "Draft extraction failed.";
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Draft extraction failed.";
}

// ─── Sub-components ────────────────────────────────────────────────────────────

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-5 text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
      {children}
    </h2>
  );
}

function RequiredMark() {
  return <span aria-hidden="true" className="ml-1 text-[var(--hermes-danger)]">*</span>;
}

function FieldError({ message }: { message: string | undefined }) {
  if (!message) return null;
  return <p className="mt-1 text-xs text-[var(--hermes-danger)]">{message}</p>;
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export function OrderFormPage({ mode }: OrderFormPageProps) {
  const isEditMode = mode === "edit";
  const { orderId = "" } = useParams();
  const navigate = useNavigate();
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const [sourceEmailText, setSourceEmailText] = useState("");

  const truckTypesQuery = useQuery({
    queryKey: ["truck-types"],
    queryFn: () => listTruckTypes(getToken),
  });

  const orderQuery = useQuery({
    queryKey: ["orders", orderId],
    queryFn: () => getOrder(orderId, getToken),
    enabled: isEditMode && orderId.length > 0,
  });

  const { register, handleSubmit, reset, watch, formState: { errors } } = useForm<OrderFormValues>({
    defaultValues: EMPTY_VALUES,
  });

  useEffect(() => {
    if (isEditMode && orderQuery.data) {
      reset(toFormValues(orderQuery.data));
    }
  }, [isEditMode, orderQuery.data, reset]);

  const watchedPrice = watch("customer_price");
  const watchedDistance = watch("distance_km");
  const watchedWeight = watch("weight_kg");

  function rangeWarning(value: string, field: "customer_price" | "distance_km" | "weight_kg"): string | null {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const num = parseFloat(trimmed);
    if (isNaN(num)) return null;
    switch (field) {
      case "customer_price":
        if (num < 50) return "Price seems unusually low";
        if (num > 50000) return "Price seems unusually high";
        break;
      case "distance_km":
        if (num < 1) return "Distance seems unusually short";
        if (num > 5000) return "Distance seems unusually long";
        break;
      case "weight_kg":
        if (num < 1) return "Weight seems unusually low";
        if (num > 40000) return "Weight seems unusually high";
        break;
    }
    return null;
  }

  const saveMutation = useMutation({
    mutationFn: async (values: OrderFormValues) => {
      const payload = toMutationPayload(values);
      if (isEditMode) {
        return updateOrder(orderId, getToken, payload);
      }
      return createOrder(getToken, payload);
    },
    onSuccess: (order) => {
      navigate(`/orders/${order.id}`);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", order.id] }),
        queryClient.invalidateQueries({ queryKey: ["orders", "summary"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "status"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "orchestrator", "timeline"] }),
      ]);
    },
  });

  const extractMutation = useMutation({
    mutationFn: async () => {
      return delegateOrderAction(getToken, {
        action: "extract_email_into_order_draft",
        source_email_text: sourceEmailText,
      });
    },
    onSuccess: (result) => {
      const extractedOrder = result.ingestion_result?.load_order;
      if (extractedOrder) {
        navigate(`/orders/${extractedOrder.id}/intake`);
      }
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["orders"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", "summary"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "status"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "orchestrator", "timeline"] }),
      ]);
    },
  });

  const isLoading =
    truckTypesQuery.isLoading || (isEditMode && orderQuery.isLoading);

  if (isEditMode && !orderId) {
    return <p className="text-sm text-[var(--hermes-danger)]">Missing order identifier.</p>;
  }

  if (isLoading) {
    return <WorkspaceLoader label="Loading…" />;
  }

  if (truckTypesQuery.isError) {
    return <p className="text-sm text-[var(--hermes-danger)]">Failed to load truck types.</p>;
  }

  if (isEditMode && orderQuery.isError) {
    return <p className="text-sm text-[var(--hermes-danger)]">Failed to load order.</p>;
  }

  const truckTypes = truckTypesQuery.data ?? [];
  const returnHref = isEditMode && orderId ? `/orders/${orderId}` : "/orders";

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Order workspace"
        title={isEditMode ? "Edit order" : "Create order"}
      />

      {!isEditMode ? (
        <p className="text-xs text-[var(--hermes-muted)]">
          Fields marked with <span className="text-[var(--hermes-danger)]">*</span> are required to create a viable order.
        </p>
      ) : null}

      {/* Status strip — no card */}
      <div className="flex items-center justify-between border-b border-[var(--hermes-border)] pb-4">
        <div className="text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
          {isEditMode ? "Order update" : "Manual order entry"}
        </div>
        {isEditMode ? (
          <StatusBadge status={orderQuery.data?.status ?? "viability_pending"} />
        ) : null}
      </div>

      {/* Email extraction — create mode only, kept as a distinct panel */}
      {!isEditMode ? (
        <SurfacePanel>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-[0.65rem] font-medium uppercase tracking-widest text-[var(--hermes-muted)]">
                Email extraction
              </h2>
              <p className="mt-2 max-w-sm text-sm leading-relaxed text-[var(--hermes-muted)]">
                Paste source email to delegate draft extraction, or fill the form below manually.
              </p>
            </div>
            <button
              className="hermes-secondary-button shrink-0 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!sourceEmailText.trim() || extractMutation.isPending}
              onClick={() => extractMutation.mutate()}
              type="button"
            >
              {extractMutation.isPending ? "Extracting..." : "Extract email into draft"}
            </button>
          </div>

          <textarea
            aria-label="Source email text"
            className="hermes-input mt-4 min-h-36 resize-y text-sm"
            onChange={(event) => setSourceEmailText(event.target.value)}
            placeholder="Paste customer email text here"
            value={sourceEmailText}
          />

          {extractMutation.data?.activity?.next_action ? (
            <p className="mt-3 text-sm text-[var(--hermes-accent)]">
              Next: {extractMutation.data.activity.next_action}
            </p>
          ) : null}
          {extractMutation.isError ? (
            <p className="mt-3 text-sm text-[var(--hermes-danger)]">
              {formatExtractError(extractMutation.error)}
            </p>
          ) : null}
        </SurfacePanel>
      ) : null}

      {/* Form — section separators, no individual cards */}
      <form
        onSubmit={handleSubmit(async (values) => {
          await saveMutation.mutateAsync(values);
        })}
      >
        <div className="divide-y divide-[var(--hermes-border)]">

          {/* Commercial */}
          <div className="py-7">
            <SectionHeading>Commercial</SectionHeading>
            <div className="grid gap-x-6 gap-y-4 md:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-xs text-[var(--hermes-muted)]">
                  Customer name<RequiredMark />
                </span>
                <input className="hermes-input text-sm" {...register("customer_name", { required: "Customer name is required" })} type="text" />
                <FieldError message={errors.customer_name?.message} />
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs text-[var(--hermes-muted)]">
                  Customer price
                </span>
                <input className="hermes-input text-sm" {...register("customer_price", { pattern: { value: /^\d*\.?\d*$/, message: "Must be a number" } })} type="text" />
                <FieldError message={errors.customer_price?.message} />
                {rangeWarning(watchedPrice, "customer_price") ? (
                  <p className="mt-1 text-xs text-amber-400/70">{rangeWarning(watchedPrice, "customer_price")}</p>
                ) : null}
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs text-[var(--hermes-muted)]">Currency</span>
                <input className="hermes-input text-sm" {...register("currency")} type="text" />
              </label>
            </div>
          </div>

          {/* Route */}
          <div className="py-7">
            <SectionHeading>Route</SectionHeading>
            <div className="grid gap-x-6 gap-y-4 md:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-xs text-[var(--hermes-muted)]">Origin<RequiredMark /></span>
                <input
                  className="hermes-input text-sm"
                  {...register("origin_text", { required: "Origin is required" })}
                  placeholder="Madrid, ES"
                  type="text"
                />
                <FieldError message={errors.origin_text?.message} />
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs text-[var(--hermes-muted)]">Destination<RequiredMark /></span>
                <input
                  className="hermes-input text-sm"
                  {...register("destination_text", { required: "Destination is required" })}
                  placeholder="Paris, FR"
                  type="text"
                />
                <FieldError message={errors.destination_text?.message} />
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs text-[var(--hermes-muted)]">
                  Distance (km)
                </span>
                <input className="hermes-input text-sm" {...register("distance_km", { pattern: { value: /^\d*\.?\d*$/, message: "Must be a number" } })} type="text" />
                <FieldError message={errors.distance_km?.message} />
                {rangeWarning(watchedDistance, "distance_km") ? (
                  <p className="mt-1 text-xs text-amber-400/70">{rangeWarning(watchedDistance, "distance_km")}</p>
                ) : null}
              </label>
            </div>
          </div>

          {/* Schedule */}
          <div className="py-7">
            <SectionHeading>Schedule</SectionHeading>
            <div className="grid gap-x-6 gap-y-4 md:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-xs text-[var(--hermes-muted)]">
                  Origin load date<RequiredMark />
                </span>
                <input
                  className="hermes-input text-sm"
                  inputMode="none"
                  onClick={openDateTimeLocalPicker}
                  onDrop={preventDateTimeLocalPaste}
                  onKeyDown={handleDateTimeLocalKeyDown}
                  onPaste={preventDateTimeLocalPaste}
                  step={60}
                  {...register("origin_load_date", { required: "Origin load date is required" })}
                  type="datetime-local"
                />
                <FieldError message={errors.origin_load_date?.message} />
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs text-[var(--hermes-muted)]">
                  Destination unload date
                </span>
                <input
                  className="hermes-input text-sm"
                  inputMode="none"
                  onClick={openDateTimeLocalPicker}
                  onDrop={preventDateTimeLocalPaste}
                  onKeyDown={handleDateTimeLocalKeyDown}
                  onPaste={preventDateTimeLocalPaste}
                  step={60}
                  {...register("destination_unload_date")}
                  type="datetime-local"
                />
              </label>
            </div>
          </div>

          {/* Cargo */}
          <div className="py-7">
            <SectionHeading>Cargo</SectionHeading>
            <div className="grid gap-x-6 gap-y-4 md:grid-cols-2">
              <label className="block md:col-span-2">
                <span className="mb-1.5 block text-xs text-[var(--hermes-muted)]">
                  Cargo description<RequiredMark />
                </span>
                <input
                  className="hermes-input text-sm"
                  {...register("cargo_description", { required: "Cargo description is required" })}
                  type="text"
                />
                <FieldError message={errors.cargo_description?.message} />
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs text-[var(--hermes-muted)]">
                  Weight (kg)
                </span>
                <input className="hermes-input text-sm" {...register("weight_kg", { pattern: { value: /^\d*\.?\d*$/, message: "Must be a number" } })} type="text" />
                <FieldError message={errors.weight_kg?.message} />
                {rangeWarning(watchedWeight, "weight_kg") ? (
                  <p className="mt-1 text-xs text-amber-400/70">{rangeWarning(watchedWeight, "weight_kg")}</p>
                ) : null}
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs text-[var(--hermes-muted)]">Truck type</span>
                <select className="hermes-input text-sm" {...register("truck_type_id")}>
                  <option value="">Select truck type</option>
                  {truckTypes.map((truckType) => (
                    <option key={truckType.id} value={String(truckType.id)}>
                      {truckType.name}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex cursor-pointer items-center gap-3 md:col-span-2">
                <input
                  className="h-4 w-4 accent-[var(--hermes-accent)]"
                  {...register("adr_required")}
                  type="checkbox"
                />
                <span className="text-sm text-[var(--hermes-muted)]">ADR required</span>
              </label>
            </div>
          </div>

        </div>

        {saveMutation.isError ? (
          <p className="mb-5 text-sm text-[var(--hermes-danger)]">{String(saveMutation.error)}</p>
        ) : null}

        <div className="flex items-center justify-start gap-3 border-t border-[var(--hermes-border)] pt-6">
          <Link
            className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 transition-colors duration-150 hover:border-white/20 hover:bg-white/[0.04]"
            to={returnHref}
          >
            Cancel
          </Link>
          <button
            className="hermes-primary-button px-5 py-2 text-sm disabled:opacity-50"
            disabled={saveMutation.isPending}
            type="submit"
          >
            {saveMutation.isPending ? "Saving..." : "Save order"}
          </button>
        </div>
      </form>
    </section>
  );
}
