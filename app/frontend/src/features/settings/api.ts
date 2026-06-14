import { useAuth } from "@clerk/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../../lib/apiClient";


export type RuntimeSettings = {
  enable_auto_carrier_search: boolean;
  enable_ingestion_smart_comms_handoff: boolean;
  enable_smart_comms_retrieval: boolean;
  enable_carrier_search_retrieval: boolean;
  ingestion_provider: string;
  ingestion_model_name: string;
  reasoning_provider: string;
  reasoning_model_name: string;
  chroma_reachable: boolean;
};

export type RuntimeSettingsUpdate = {
  enable_auto_carrier_search?: boolean;
  enable_ingestion_smart_comms_handoff?: boolean;
  enable_smart_comms_retrieval?: boolean;
  enable_carrier_search_retrieval?: boolean;
};


export function getRuntimeSettings(getToken: () => Promise<string | null>) {
  return apiClient<RuntimeSettings>("/settings/runtime", getToken);
}

export function updateRuntimeSettings(
  getToken: () => Promise<string | null>,
  payload: RuntimeSettingsUpdate,
) {
  return apiClient<RuntimeSettings>("/settings/runtime", getToken, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}


export function useRuntimeSettings() {
  const { getToken } = useAuth();

  return useQuery({
    queryKey: ["settings", "runtime"],
    queryFn: () => getRuntimeSettings(getToken),
  });
}

export function useUpdateRuntimeSettings() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: RuntimeSettingsUpdate) =>
      updateRuntimeSettings(getToken, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "runtime"] });
    },
  });
}
