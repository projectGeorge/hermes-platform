import { useAuth } from "@clerk/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, streamSSE } from "../../lib/apiClient";

export type SmartCommsContextType = "dashboard" | "orders_list" | "load_order" | "carrier_match" | "intake_review" | "settings";
export type SmartCommsMessageRole = "user" | "assistant" | "system";

export type SmartCommsConversation = {
  id: string;
  user_id: string;
  context_type: SmartCommsContextType;
  context_id: string | null;
  route_path: string;
  title: string | null;
  created_at: string;
  updated_at: string;
};

export type SmartCommsMessage = {
  id: string;
  conversation_id: string;
  role: SmartCommsMessageRole;
  content: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

export async function resolveConversation(
  getToken: () => Promise<string | null>,
  contextType: SmartCommsContextType,
  routePath: string,
  contextId?: string,
): Promise<SmartCommsConversation> {
  return apiClient<SmartCommsConversation>(
    "/smart-comms/conversations/resolve",
    getToken,
    {
      method: "POST",
      body: JSON.stringify({
        context_type: contextType,
        route_path: routePath,
        context_id: contextId ?? null,
      }),
    },
  );
}

export function useResolveConversation(
  contextType: SmartCommsContextType,
  routePath: string,
  contextId?: string,
  enabled = true,
) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["smart-comms", "conversation", contextType, contextId],
    queryFn: () => resolveConversation(getToken, contextType, routePath, contextId),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useStreamMessage(conversationId: string | undefined) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async ({
      content,
      onChunk,
    }: {
      content: string;
      onChunk?: (chunk: string) => void;
    }) => {
      if (!conversationId) throw new Error("No conversation");

      let fullResponse = "";
      for await (const event of streamSSE(
        `/smart-comms/conversations/${conversationId}/messages/stream`,
        getToken,
        { content },
      )) {
        if (event.event === "conversation") {
          queryClient.invalidateQueries({ queryKey: ["agents", "status"] });
          queryClient.invalidateQueries({ queryKey: ["agents", "orchestrator", "timeline"] });
          queryClient.invalidateQueries({ queryKey: ["orders", "summary"] });
        } else if (event.event === "delta") {
          const payload = JSON.parse(event.data) as { chunk: string };
          fullResponse += payload.chunk;
          onChunk?.(payload.chunk);
        } else if (event.event === "error") {
          const payload = JSON.parse(event.data) as { detail: string };
          throw new Error(payload.detail);
        }
      }
      return fullResponse;
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["smart-comms"] });
      queryClient.invalidateQueries({ queryKey: ["agents", "status"] });
      queryClient.invalidateQueries({ queryKey: ["agents", "orchestrator", "timeline"] });
      queryClient.invalidateQueries({ queryKey: ["orders", "summary"] });
    },
  });

  return mutation;
}


export async function getConversationMessages(
  getToken: () => Promise<string | null>,
  conversationId: string,
): Promise<SmartCommsMessage[]> {
  return apiClient<SmartCommsMessage[]>(
    `/smart-comms/conversations/${conversationId}/messages`,
    getToken,
  );
}


export function useConversationMessages(conversationId: string | undefined, enabled = true) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: ["smart-comms", "messages", conversationId],
    queryFn: () => getConversationMessages(getToken, conversationId!),
    enabled: enabled && !!conversationId,
    staleTime: 60_000,
  });
}

export async function deleteConversation(
  getToken: () => Promise<string | null>,
  conversationId: string,
): Promise<void> {
  await apiClient<void>(
    `/smart-comms/conversations/${conversationId}`,
    getToken,
    { method: "DELETE" },
  );
}

export function useDeleteConversation() {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (conversationId: string) => deleteConversation(getToken, conversationId),
    onSuccess: (_, conversationId) => {
      queryClient.removeQueries({ queryKey: ["smart-comms", "messages", conversationId] });
      queryClient.invalidateQueries({ queryKey: ["smart-comms", "conversation"] });
    },
  });
}
