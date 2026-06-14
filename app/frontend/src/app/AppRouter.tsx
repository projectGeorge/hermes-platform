import type { RouteObject } from "react-router-dom";

import { SignInPage } from "../features/auth/SignInPage";
import { SignUpPage } from "../features/auth/SignUpPage";
import { CarrierMatchPage } from "../features/carrier/CarrierMatchPage";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { LandingPage } from "../features/landing/LandingPage";
import { ExecutionMonitoringPage } from "../features/monitoring/ExecutionMonitoringPage";
import { OrderIntakePage } from "../features/intake/OrderIntakePage";
import { OrderDetailPage } from "../features/orders/OrderDetailPage";
import { OrderFormPage } from "../features/orders/OrderFormPage";
import { OrdersListPage } from "../features/orders/OrdersListPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { ProtectedRoute } from "./routes/ProtectedRoute";


export const routes: RouteObject[] = [
  { path: "/", element: <LandingPage /> },
  { path: "/sign-in/*", element: <SignInPage /> },
  { path: "/sign-up/*", element: <SignUpPage /> },
  {
    element: <ProtectedRoute />,
    children: [
      { path: "/dashboard", element: <DashboardPage /> },
      { path: "/orders", element: <OrdersListPage /> },
      { path: "/orders/new", element: <OrderFormPage mode="create" /> },
      { path: "/orders/:orderId", element: <OrderDetailPage /> },
      { path: "/orders/:orderId/edit", element: <OrderFormPage mode="edit" /> },
      { path: "/orders/:orderId/intake", element: <OrderIntakePage /> },
      { path: "/orders/:orderId/carrier-match", element: <CarrierMatchPage /> },
      { path: "/orders/:orderId/monitoring", element: <ExecutionMonitoringPage /> },
      { path: "/settings", element: <SettingsPage /> },
    ],
  },
];
