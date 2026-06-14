import { useLocation, useParams } from "react-router-dom";

import type { SmartCommsContextType } from "../../features/smart-comms/api";

export type ShellPageContext = {
  contextType: SmartCommsContextType;
  contextId: string | undefined;
  routePath: string;
  label: string;
};

export function useShellPageContext(): ShellPageContext {
  const location = useLocation();
  const params = useParams();
  const path = location.pathname;

  if (path === "/dashboard") {
    return { contextType: "dashboard", contextId: undefined, routePath: path, label: "Dashboard" };
  }

  if (path === "/orders") {
    return { contextType: "orders_list", contextId: undefined, routePath: path, label: "Orders" };
  }

  if (path === "/settings") {
    return { contextType: "settings", contextId: undefined, routePath: path, label: "Settings" };
  }

  if (path === "/orders/new") {
    return { contextType: "load_order", contextId: undefined, routePath: path, label: "New order" };
  }

  if (params.orderId && path.includes("/carrier-match")) {
    return {
      contextType: "carrier_match",
      contextId: params.orderId,
      routePath: path,
      label: "Carrier match",
    };
  }

  if (params.orderId && path.includes("/intake")) {
    return {
      contextType: "intake_review",
      contextId: params.orderId,
      routePath: path,
      label: "Intake review",
    };
  }

  if (params.orderId) {
    return {
      contextType: "load_order",
      contextId: params.orderId,
      routePath: path,
      label: `Order ${params.orderId.slice(0, 8)}`,
    };
  }

  return { contextType: "dashboard", contextId: undefined, routePath: path, label: "Hermes" };
}
