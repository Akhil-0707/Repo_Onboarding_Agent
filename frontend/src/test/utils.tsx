import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { RouteObject } from "react-router";
import { vi } from "vitest";

import { AuthProvider } from "../lib/auth";
import { ThemeProvider } from "../lib/theme";

export function renderWithProviders(
  ui: ReactElement,
  {
    path = "/",
    routes,
    auth = false,
  }: { path?: string; routes?: RouteObject[]; auth?: boolean } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  });
  const router = createMemoryRouter(routes ?? [{ path: "*", element: ui }], {
    initialEntries: [path],
  });
  return {
    router,
    queryClient,
    ...render(
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          {auth ? (
            <AuthProvider>
              <RouterProvider router={router} />
            </AuthProvider>
          ) : (
            <RouterProvider router={router} />
          )}
        </QueryClientProvider>
      </ThemeProvider>,
    ),
  };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type FetchHandler = (url: string, init?: RequestInit) => Response | Promise<Response>;

export function mockFetch(handler: FetchHandler) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    return handler(url, init);
  });
}
