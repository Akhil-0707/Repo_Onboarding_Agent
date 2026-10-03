import { screen, waitFor, within } from "@testing-library/react";
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

  function renderProgress(stream: () => Response, onPost?: (body: unknown) => Response) {
    const spy = mockFetch((url, init) => {
      if (url.endsWith("/api/auth/refresh")) return jsonResponse({ access: "a", user });
      if (url.endsWith("/job/stream")) return stream();
      if (url.endsWith("/api/repos") && init?.method === "POST" && onPost) {
        return onPost(JSON.parse(String(init.body)));
      }
      return jsonResponse(makeRepo({ status: "ingesting" }));
    });
    const result = renderWithProviders(<></>, {
      path: "/repos/repo1/progress",
      routes: [
        { path: "/repos/:repoId/progress", element: <IngestionPage /> },
        { path: "/repos/:repoId", element: <p>Workspace opened</p> },
      ],
      auth: true,
    });
    return { spy, ...result };
  }

  const event = (name: string, data: unknown) =>
    `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;

  it("explains a pause while the model is offline", async () => {
    renderProgress(() =>
      sseResponse([event("snapshot", makeJob({ status: "waiting_for_model", progress: 70 }))]),
    );
    expect(await screen.findByText(/The AI model is offline/)).toBeInTheDocument();
  });

  it("opens the workspace when the job is done", async () => {
    const { router } = renderProgress(() =>
      sseResponse([
        event("snapshot", makeJob({ status: "done", progress: 100 })),
        event("end", { status: "done" }),
      ]),
    );
    expect(await screen.findByText("Finished, opening workspace…")).toBeInTheDocument();
    expect(await screen.findByText("Workspace opened", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/repos/repo1");
  });

  it("retries a failed analysis and reconnects to the new job", async () => {
    let streams = 0;
    const posted: unknown[] = [];
    renderProgress(
      () => {
        streams += 1;
        const job =
          streams === 1
            ? makeJob({ status: "failed", error: "Clone timed out" })
            : makeJob({ status: "running", progress: 10 });
        return sseResponse([event("snapshot", job)]);
      },
      (body) => {
        posted.push(body);
        return jsonResponse(
          { repository: makeRepo(), job: makeJob(), created: true, cached: false },
          201,
        );
      },
    );
    expect(await screen.findByText("Clone timed out")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again|retry/i }));
    await waitFor(() => expect(screen.queryByText("Clone timed out")).not.toBeInTheDocument());
    expect(posted).toEqual([{ url: makeRepo().url }]);
    expect(streams).toBe(2);
  });
});
