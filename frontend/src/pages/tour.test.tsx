import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Analysis } from "../api/types";
import { parseStep } from "../lib/tour";
import { makeAnalysis, makeRepo } from "../test/fixtures";
import { jsonResponse, mockFetch, renderWithProviders } from "../test/utils";
import { TourPage } from "./TourPage";

vi.mock("../lib/highlight", async (original) => {
  const actual = await original<typeof import("../lib/highlight")>();
  return { ...actual, highlight: async (code: string) => actual.plainTokens(code) };
});

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

function mockBackend(analysis: Analysis = makeAnalysis()) {
  return mockFetch((url) => {
    if (url.endsWith("/api/auth/refresh")) return jsonResponse({ access: "a", user });
    if (url.endsWith("/analysis")) return jsonResponse(analysis);
    if (url.includes("/files?path=")) {
      const path = decodeURIComponent(url.split("path=")[1] ?? "");
      return jsonResponse({
        path,
        language: "python",
        size: 10,
        lines: 30,
        start_line: 1,
        end_line: 30,
        content: Array.from({ length: 30 }, (_, i) => `${path} line ${i + 1}`).join("\n"),
        symbols: [],
        github_url: `https://github.com/acme/tool/blob/abc/${path}`,
      });
    }
    return jsonResponse(makeRepo());
  });
}

function renderTour(path = "/repos/repo1/tour") {
  return renderWithProviders(<></>, {
    path,
    routes: [
      { path: "/repos/:repoId/tour", element: <TourPage /> },
      { path: "/repos/:repoId", element: <p>Workspace</p> },
    ],
    auth: true,
  });
}

function highlightedLines() {
  return [...document.querySelectorAll("[data-highlighted]")].map((el) =>
    el.getAttribute("data-line"),
  );
}

describe("TourPage", () => {
  it("walks through the steps with buttons and arrow keys", async () => {
    mockBackend();
    const { router } = renderTour();

    expect(await screen.findByRole("heading", { name: "Start-up" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
    expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
    expect(await screen.findByText("app/main.py line 30")).toBeInTheDocument();
    expect(highlightedLines()).toEqual(["8", "9", "10", "11"]);
    expect(screen.getByRole("button", { name: "← Previous" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Next →" }));
    expect(screen.getByRole("heading", { name: "Routing" })).toBeInTheDocument();
    expect(screen.getByText("Flow trace")).toBeInTheDocument();
    expect(router.state.location.search).toBe("?step=2");
    expect(await screen.findByText("app/routes.py line 1")).toBeInTheDocument();
    expect(highlightedLines()).toEqual([]);

    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(screen.getByRole("heading", { name: "Service" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "3");
    fireEvent.keyDown(window, { key: "ArrowRight" }); // already at the end
    expect(router.state.location.search).toBe("?step=3");

    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(screen.getByRole("heading", { name: "Routing" })).toBeInTheDocument();
  });

  it("opens a step from the URL, jumps from the step list and finishes", async () => {
    mockBackend();
    const { router } = renderTour("/repos/repo1/tour?step=3");

    expect(await screen.findByRole("heading", { name: "Service" })).toBeInTheDocument();
    const steps = screen.getByRole("navigation", { name: "Tour steps" });
    expect(steps.querySelector("[aria-current=step]")).toHaveTextContent("3. Service");

    await userEvent.click(screen.getByRole("button", { name: "1. Start-up" }));
    expect(router.state.location.search).toBe("?step=1");

    await userEvent.click(screen.getByRole("button", { name: "3. Service" }));
    await userEvent.click(screen.getByRole("link", { name: "Finish" }));
    expect(router.state.location.pathname).toBe("/repos/repo1");
    expect(router.state.location.search).toBe("?tab=tour");
  });

  it("ignores arrow keys while typing in a field", async () => {
    mockBackend();
    const { router } = renderTour();
    await screen.findByRole("heading", { name: "Start-up" });
    const input = document.createElement("input");
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: "ArrowRight" });
    expect(router.state.location.search).toBe("");
    input.remove();
  });

  it("explains when the tour is not ready yet", async () => {
    const analysis = makeAnalysis({ status: "running" });
    analysis.sections.tour = { status: "running", error: "", updated_at: null, data: null };
    mockBackend(analysis);
    renderTour();
    expect(await screen.findByText("Writing the guided tour…")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Back to workspace" })).toBeInTheDocument();
  });
});

describe("parseStep", () => {
  it("clamps the 1-based URL step to a 0-based index", () => {
    expect(parseStep(null, 5)).toBe(0);
    expect(parseStep("3", 5)).toBe(2);
    expect(parseStep("99", 5)).toBe(4);
    expect(parseStep("-2", 5)).toBe(0);
    expect(parseStep("abc", 5)).toBe(0);
    expect(parseStep("2", 0)).toBe(0);
  });
});
