import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { User } from "../api/auth";
import { RequireAuth } from "../components/RequireAuth";
import { UserMenu } from "../components/UserMenu";
import { AuthCallbackPage } from "../pages/AuthCallbackPage";
import { LoginPage } from "../pages/LoginPage";
import { jsonResponse, mockFetch, renderWithProviders } from "../test/utils";

const user: User = {
  id: "65f0c0ffee",
  username: "octo",
  name: "Octo Cat",
  email: "octo@example.com",
  avatar_url: "",
  github_connected: true,
  private_repo_access: false,
  date_joined: "2026-10-01T00:00:00Z",
};

const expired = () =>
  jsonResponse({ error: { code: "session_expired", message: "expired", details: null } }, 401);

describe("RequireAuth", () => {
  const routes = [
    {
      path: "/dashboard",
      element: (
        <RequireAuth>
          <p>secret dashboard</p>
        </RequireAuth>
      ),
    },
    { path: "/login", element: <p>login page</p> },
  ];

  it("redirects anonymous users to login with a next param", async () => {
    mockFetch(() => expired());
    const { router } = renderWithProviders(<></>, { path: "/dashboard?x=1", routes, auth: true });

    expect(await screen.findByText("login page")).toBeInTheDocument();
    expect(router.state.location.search).toBe(`?next=${encodeURIComponent("/dashboard?x=1")}`);
  });

  it("restores the session silently via the refresh cookie", async () => {
    const spy = mockFetch((url) =>
      url.endsWith("/api/auth/refresh") ? jsonResponse({ access: "a1", user }) : expired(),
    );
    renderWithProviders(<></>, { path: "/dashboard", routes, auth: true });

    expect(await screen.findByText("secret dashboard")).toBeInTheDocument();
    const headers = new Headers(spy.mock.calls[0]?.[1]?.headers);
    expect(headers.get("X-RepoGuide-Client")).toBe("web");
  });
});

describe("AuthCallbackPage", () => {
  const routes = [
    { path: "/auth/callback", element: <AuthCallbackPage /> },
    { path: "/repos/1", element: <p>repo page</p> },
    { path: "/login", element: <p>login page</p> },
  ];

  it("exchanges the one-time code exactly once and goes to next", async () => {
    const spy = mockFetch((url) =>
      url.endsWith("/api/auth/exchange") ? jsonResponse({ access: "a1", user }) : expired(),
    );
    renderWithProviders(<></>, {
      path: "/auth/callback?code=abc&next=%2Frepos%2F1",
      routes,
      auth: true,
    });

    expect(await screen.findByText("repo page")).toBeInTheDocument();
    const exchanges = spy.mock.calls.filter(([url]) => String(url).endsWith("/api/auth/exchange"));
    expect(exchanges).toHaveLength(1);
    expect(JSON.parse(String(exchanges[0]?.[1]?.body))).toEqual({ code: "abc" });
  });

  it("ignores an unsafe next destination", async () => {
    mockFetch((url) =>
      url.endsWith("/api/auth/exchange") ? jsonResponse({ access: "a1", user }) : expired(),
    );
    const { router } = renderWithProviders(<></>, {
      path: "/auth/callback?code=abc&next=%2F%2Fevil.com",
      routes: [...routes, { path: "/dashboard", element: <p>dashboard</p> }],
      auth: true,
    });
    expect(await screen.findByText("dashboard")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/dashboard");
  });

  it("shows the error from GitHub", async () => {
    mockFetch(() => expired());
    renderWithProviders(<></>, {
      path: "/auth/callback?error=GitHub+sign-in+was+cancelled.",
      routes,
      auth: true,
    });
    expect(await screen.findByText("GitHub sign-in was cancelled.")).toBeInTheDocument();
  });

  it("shows an error when the code has expired", async () => {
    mockFetch((url) =>
      url.endsWith("/api/auth/exchange")
        ? jsonResponse(
            { error: { code: "invalid_code", message: "This sign-in link has expired." } },
            400,
          )
        : expired(),
    );
    renderWithProviders(<></>, { path: "/auth/callback?code=old", routes, auth: true });
    expect(await screen.findByText("This sign-in link has expired.")).toBeInTheDocument();
  });
});

describe("LoginPage", () => {
  it("requests private repo access only when asked", async () => {
    mockFetch(() => expired());
    renderWithProviders(<></>, {
      path: "/login?next=%2Fsettings",
      routes: [{ path: "/login", element: <LoginPage /> }],
      auth: true,
    });

    const link = await screen.findByRole("link", { name: /continue with github/i });
    expect(link).toHaveAttribute("href", "/api/auth/github/login?next=%2Fsettings");

    await userEvent.click(screen.getByRole("checkbox"));
    expect(link).toHaveAttribute("href", "/api/auth/github/login?next=%2Fsettings&private=1");
  });
});

describe("UserMenu", () => {
  it("signs out through the API", async () => {
    const spy = mockFetch((url) => {
      if (url.endsWith("/api/auth/refresh")) return jsonResponse({ access: "a1", user });
      return new Response(null, { status: 204 });
    });
    renderWithProviders(<></>, {
      routes: [
        { path: "/", element: <UserMenu /> },
        { path: "/settings", element: <p>settings</p> },
      ],
      auth: true,
    });

    await userEvent.click(await screen.findByRole("button", { name: /account menu for octo/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /sign out/i }));

    await waitFor(() =>
      expect(spy.mock.calls.some(([url]) => String(url).endsWith("/api/auth/logout"))).toBe(true),
    );
    expect(await screen.findByRole("link", { name: "Sign in" })).toBeInTheDocument();
  });
});
