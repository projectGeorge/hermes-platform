import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ClerkProvider } from "@clerk/react";
import { RouterProvider, createBrowserRouter } from "react-router-dom";

import "leaflet/dist/leaflet.css";
import "./index.css";
import { routes } from "./app/AppRouter";
import { AppProviders } from "./app/providers/AppProviders";
import { clerkAppearance } from "./features/auth/clerkAppearance";


const router = createBrowserRouter(routes);
const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ClerkProvider
      afterSignOutUrl="/"
      appearance={clerkAppearance}
      publishableKey={publishableKey}
    >
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>
    </ClerkProvider>
  </StrictMode>,
);
