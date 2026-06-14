import { apiClient } from "../../lib/apiClient";


export type CurrentUser = {
  id: string;
  email: string;
  operator_name: string;
  auth_id: string;
};


export function getCurrentUser(getToken: () => Promise<string | null>) {
  return apiClient<CurrentUser>("/users/me", getToken);
}
