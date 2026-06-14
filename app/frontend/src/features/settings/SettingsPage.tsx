import { useState } from "react";

import { PageHeader } from "../../app/ui/PageHeader";
import {
  useRuntimeSettings,
  useUpdateRuntimeSettings,
} from "./api";


function ToggleField({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <div className="flex items-start justify-between gap-6 py-4">
      <div className="min-w-0">
        <p className="text-sm font-medium text-white">{label}</p>
        <p className="mt-1 text-xs leading-relaxed text-[var(--hermes-muted)]">
          {description}
        </p>
      </div>
      <button
        aria-checked={checked}
        aria-label={label}
        className={`mt-0.5 flex h-5 w-9 shrink-0 items-center rounded-full p-0.5 transition-colors duration-200 ${
          checked
            ? "bg-[var(--hermes-accent)]"
            : "bg-slate-700"
        }`}
        onClick={onChange}
        role="switch"
        type="button"
      >
        <span
          className={`block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
            checked ? "translate-x-4" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}


function InfoRow({
  label,
  detail,
  status,
}: {
  label: string;
  detail: string;
  status?: "connected" | "disconnected" | "unknown";
}) {
  const dotColor =
    status === "connected"
      ? "bg-emerald-400"
      : status === "disconnected"
        ? "bg-red-400"
        : "bg-slate-500";

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs font-medium text-[var(--hermes-muted)]">{label}</span>
      <span className="text-xs text-[var(--hermes-text)]">{detail}</span>
      <span className={`ml-auto h-2 w-2 shrink-0 rounded-full ${dotColor}`} />
    </div>
  );
}


export function SettingsPage() {
  const { data: settings, isLoading, isError } = useRuntimeSettings();
  const updateMutation = useUpdateRuntimeSettings();
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  if (isLoading || isError || !settings) {
    return (
      <div>
        <PageHeader
          title="Settings"
          description="Control AI agent behavior and runtime configuration."
        />
        <div className="py-12 text-center text-sm text-[var(--hermes-muted)]">
          {isLoading ? "Loading settings..." : "Could not load settings."}
        </div>
      </div>
    );
  }

  const handleToggle = async (
    key: "enable_auto_carrier_search" | "enable_ingestion_smart_comms_handoff" | "enable_smart_comms_retrieval" | "enable_carrier_search_retrieval",
  ) => {
    const current = settings[key];
    try {
      await updateMutation.mutateAsync({ [key]: !current });
      setSaveMessage("Saved.");
      setTimeout(() => setSaveMessage(null), 2000);
    } catch {
      setSaveMessage("Save failed.");
    }
  };

  const chromaStatus: "connected" | "disconnected" | "unknown" =
    settings.chroma_reachable ? "connected" : "disconnected";

  return (
    <div>
      <div className="flex items-center justify-between">
        <PageHeader
          title="Settings"
          description="Control AI agent behavior and runtime configuration."
        />
        {saveMessage ? (
          <span className="mr-2 rounded bg-[var(--hermes-accent-soft)] px-3 py-1 text-xs font-medium text-[var(--hermes-accent)]">
            {saveMessage}
          </span>
        ) : null}
      </div>

      <div className="mt-8 space-y-10">
        {/* ── Agent Behavior ── */}
        <section>
          <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--hermes-muted)]">
            Agent Behavior
          </h2>
          <div className="divide-y divide-[var(--hermes-border)]">
            <ToggleField
              label="Auto carrier search"
              description="When enabled, the orchestrator will automatically trigger carrier search after viability confirmation."
              checked={settings.enable_auto_carrier_search}
              onChange={() => handleToggle("enable_auto_carrier_search")}
            />
            <ToggleField
              label="Ingestion to Smart Comms handoff"
              description="When ingestion cannot fully extract an order draft, automatically create a clarification conversation in Smart Comms."
              checked={settings.enable_ingestion_smart_comms_handoff}
              onChange={() => handleToggle("enable_ingestion_smart_comms_handoff")}
            />
          </div>
        </section>

        {/* ── Retrieval / Memory ── */}
        <section>
          <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--hermes-muted)]">
            Retrieval / Memory
          </h2>
          <div className="divide-y divide-[var(--hermes-border)]">
            <ToggleField
              label="Smart Comms memory retrieval"
              description="Allow Smart Comms to retrieve historical context from ChromaDB when generating responses."
              checked={settings.enable_smart_comms_retrieval}
              onChange={() => handleToggle("enable_smart_comms_retrieval")}
            />
            <ToggleField
              label="Carrier search memory retrieval"
              description="Allow carrier search to retrieve similar past orders from ChromaDB to enrich evaluation."
              checked={settings.enable_carrier_search_retrieval}
              onChange={() => handleToggle("enable_carrier_search_retrieval")}
            />
          </div>
        </section>

        {/* ── Runtime Info ─ */}
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-[var(--hermes-muted)]">
            Runtime Info
          </h2>
          <div className="space-y-2">
            <InfoRow
              label="Ingestion AI"
              detail={
                settings.ingestion_model_name
                  ? `${settings.ingestion_provider} / ${settings.ingestion_model_name}`
                  : `${settings.ingestion_provider} (no model configured)`
              }
            />
            <InfoRow
              label="Reasoning AI"
              detail={
                settings.reasoning_model_name
                  ? `${settings.reasoning_provider} / ${settings.reasoning_model_name}`
                  : `${settings.reasoning_provider} (no model configured)`
              }
            />
            <InfoRow
              label="ChromaDB"
              detail={chromaStatus === "connected" ? "Local persistent runtime available" : "Local persistent runtime unavailable"}
              status={chromaStatus}
            />
          </div>
        </section>
      </div>
    </div>
  );
}
