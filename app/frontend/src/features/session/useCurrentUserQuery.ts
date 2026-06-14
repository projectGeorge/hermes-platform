import { useAuth } from "@clerk/react";
import { useQuery } from "@tanstack/react-query";

import { getCurrentUser } from "./api";


export function useCurrentUserQuery() {
  const { getToken } = useAuth();

  return useQuery({
    queryKey: ["session", "me"],
    queryFn: () => getCurrentUser(getToken),
    staleTime: 10 * 60_000,
  });
}
