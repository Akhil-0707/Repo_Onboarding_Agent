import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";
import type { RouteObject } from "react-router";

import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { AuthProvider } from "./lib/auth";
import { ThemeProvider } from "./lib/theme";
import { AuthCallbackPage } from "./pages/AuthCallbackPage";
import { DashboardPage } from "./pages/DashboardPage";
import { IngestionPage } from "./pages/IngestionPage";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TourPage } from "./pages/TourPage";
import { WorkspacePage } from "./pages/WorkspacePage";

// eslint-disable-next-line react-refresh/only-export-components
export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { index: true, element: <LandingPage /> },
      { path: "login", element: <LoginPage /> },
      { path: "auth/callback", element: <AuthCallbackPage /> },
      {
        path: "dashboard",
        element: (
          <RequireAuth>
            <DashboardPage />
          </RequireAuth>
        ),
      },
      {
        path: "repos/:repoId",
        element: (
          <RequireAuth>
            <WorkspacePage />
          </RequireAuth>
        ),
      },
      {
        path: "repos/:repoId/tour",
        element: (
          <RequireAuth>
            <TourPage />
          </RequireAuth>
        ),
      },
      {
        path: "repos/:repoId/progress",
        element: (
          <RequireAuth>
            <IngestionPage />
          </RequireAuth>
        ),
      },
      {
        path: "settings",
        element: (
          <RequireAuth>
            <SettingsPage />
          </RequireAuth>
        ),
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

// eslint-disable-next-line react-refresh/only-export-components
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 10_000, refetchOnWindowFocus: false, retry: 1 },
    },
  });
}

export function App() {
  const [queryClient] = useState(createQueryClient);
  const [router] = useState(() => createBrowserRouter(routes));
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
