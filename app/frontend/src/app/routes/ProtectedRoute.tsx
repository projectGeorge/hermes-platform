import { useAuth } from "@clerk/react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { AppShell } from "../layout/AppShell";


export function ProtectedRoute() {
  const location = useLocation();
  const { isLoaded, isSignedIn } = useAuth();

  if (!isLoaded) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-white/10 border-t-[var(--hermes-accent)]" />
      </div>
    );
  }

  if (!isSignedIn) {
    return <Navigate replace to="/sign-in" state={{ from: location.pathname }} />;
  }

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
