import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { makeJob, makeRepo } from "../test/fixtures";
import { jsonResponse, mockFetch, renderWithProviders, sseResponse } from "../test/utils";
import { DashboardPage } from "./DashboardPage";
import { IngestionPage } from "./IngestionPage";

const user = {
  id: "u1",
  username: "octo",
  name: "Octo",
  email: "",
  avatar_url: "",
  github_connected: true,
  private_repo_access: false,
  date_joined: "2026-10-01T00:00:00Z",
};

describe("DashboardPage", () => {
  it("lists repositories with status badges", async () => {
    mockFetch((url) => {
      if (url.endsWith("/api/auth/refresh")) return jsonResponse({ access: "a", user });
      return jsonResponse({
        count: 2,
        next: null,
        previous: null,
        results: [
          makeRepo(),
          makeRepo({ id: "r2", full_name: "acme/broken", status: "failed", error: "Too big" }),
        ],
      });
    });
    renderWithProviders(<DashboardPage />, { auth: true });

    expect(await screen.findByText("acme/tool")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Too big")).toBeInTheDocument();
  });

  it("starts an analysis and goes to the progress page", async () => {
    mockFetch((url, init) => {
      if (url.endsWith("/api/auth/refresh")) return jsonResponse({ access: "a", user });
      if (init?.method === "POST") {
        return jsonResponse(
          {
            repository: makeRepo({ id: "new1", status: "queued" }),
            job: makeJob(),
            created: true,
            cached: false,
          },
          201,
        );
      }
      return jsonResponse({ count: 0, next: null, previous: null, results: [] });
    });
    const { router } = renderWithProviders(<></>, {
      path: "/dashboard?analyze=acme%2Ftool",
      routes: [
        { path: "/dashboard", element: <DashboardPage /> },
        { path: "/repos/:repoId/progress", element: <p>progress page</p> },
      ],
      auth: true,
    });

    const input = await screen.findByLabelText("GitHub repository URL");
    expect(input).toHaveValue("https://github.com/acme/tool");
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByText("progress page")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/repos/new1/progress");
  });

  it("shows the API error when the analysis cannot start", async () => {
    mockFetch((url, init) => {
      if (url.endsWith("/api/auth/refresh")) return jsonResponse({ access: "a", user });
      if (init?.method === "POST") {
        return jsonResponse(
          { error: { code: "limit_exceeded", message: "acme/huge is about 900 MB" } },
          400,
        );
      }
      return jsonResponse({ count: 0, next: null, previous: null, results: [] });
    });
    renderWithProviders(<DashboardPage />, { auth: true });
    await userEvent.type(await screen.findByLabelText("GitHub repository URL"), "acme/huge");
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("acme/huge is about 900 MB");
  });
});

describe("IngestionPage", () => {
  it("renders live steps from the SSE stream", async () => {
    const snapshot = makeJob();
    mockFetch((url) => {
      if (url.endsWith("/api/auth/refresh")) return jsonResponse({ access: "a", user });
      if (url.endsWith("/job/stream")) {
        return sseResponse([
          `event: snapshot\ndata: ${JSON.stringify(snapshot)}\n\n`,
          `event: step\ndata: ${JSON.stringify({ type: "step", key: "clone", status: "done", message: "Shallow clone complete", job_progress: 50 })}\n\n`,
          `event: log\ndata: ${JSON.stringify({ type: "log", key: "parse", ts: "2026-10-01T00:00:02Z", level: "info", message: "Parsed 12 files" })}\n\n`,
          `event: job\ndata: ${JSON.stringify({ type: "job", status: "failed", error: "Too many files" })}\n\n`,
          `event: end\ndata: {"status": "failed"}\n\n`,
        ]);
      }
      return jsonResponse(makeRepo({ status: "failed" }));
    });
    renderWithProviders(<></>, {
      path: "/repos/repo1/progress",
      routes: [{ path: "/repos/:repoId/progress", element: <IngestionPage /> }],
      auth: true,
    });

    const steps = await screen.findByRole("list", { name: "Ingestion steps" });
    expect(await within(steps).findByText("Shallow clone complete")).toBeInTheDocument();
    expect(await screen.findByText("Analysis failed")).toBeInTheDocument();
    expect(screen.getByText("Too many files")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
  });
});
