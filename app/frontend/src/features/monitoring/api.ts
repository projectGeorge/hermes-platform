import { useAuth } from "@clerk/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type ExecutionMonitoringReadModel,
  getExecutionMonitoring,
  refreshExecutionMonitoring,
} from "../orders/api";


export function useExecutionMonitoring(orderId: string | undefined) {
  const { getToken } = useAuth();

  return useQuery({
    queryKey: ["monitoring", "execution", orderId],
    queryFn: () => getExecutionMonitoring(orderId ?? "", getToken),
    enabled: Boolean(orderId),
  });
}


export function useRefreshExecutionMonitoring(orderId: string | undefined) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => refreshExecutionMonitoring(orderId ?? "", getToken),
    onSuccess: async (data: ExecutionMonitoringReadModel) => {
      queryClient.setQueryData(["monitoring", "execution", orderId], data);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["monitoring", "execution", orderId] }),
        queryClient.invalidateQueries({ queryKey: ["orders", orderId] }),
        queryClient.invalidateQueries({ queryKey: ["orders"] }),
        queryClient.invalidateQueries({ queryKey: ["orders", "summary"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "status"] }),
        queryClient.invalidateQueries({ queryKey: ["agents", "orchestrator", "timeline"] }),
      ]);
    },
  });
}
