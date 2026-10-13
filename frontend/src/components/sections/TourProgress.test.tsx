import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeJob, makeStep } from "../../test/fixtures";
import { jsonResponse, mockFetch, renderWithProviders, sseResponse } from "../../test/utils";
import { TourProgress } from "./TourProgress";

describe("TourProgress", () => {
  it("shows the live stage, what the model is doing and how long it has taken", async () => {
    const job = makeJob({
      steps: [
        makeStep({
          key: "analyze",
          label: "AI analysis",
          status: "running",
          phase: "writing",
          progress: 60,
          started_at: new Date(Date.now() - 95_000).toISOString(),
        }),
      ],
    });
    mockFetch((url) =>
      url.endsWith("/job/stream")
        ? sseResponse([`event: snapshot\ndata: ${JSON.stringify(job)}\n\n`])
        : jsonResponse({}),
    );
    renderWithProviders(<TourProgress repoId="repo1" />, { auth: true });

    expect(await screen.findByText(/writing the stops/)).toBeInTheDocument();
    expect(screen.getByText(/1:3\d elapsed · usually 3 to 4 minutes/)).toBeInTheDocument();
    const bar = screen.getByRole("progressbar", { name: "Tour progress" });
    expect(Number(bar.getAttribute("aria-valuenow"))).toBeGreaterThanOrEqual(60);
    expect(screen.getByText("Reading the code")).toBeInTheDocument();
    expect(screen.getByText("Checking every file and line")).toHaveClass("text-slate-400");
  });

  it("says so when the model server is offline", async () => {
    const job = makeJob({
      status: "waiting_for_model",
      steps: [makeStep({ key: "analyze", label: "AI analysis", status: "waiting" })],
    });
    mockFetch((url) =>
      url.endsWith("/job/stream")
        ? sseResponse([`event: snapshot\ndata: ${JSON.stringify(job)}\n\n`])
        : jsonResponse({}),
    );
    renderWithProviders(<TourProgress repoId="repo1" />, { auth: true });
    expect(await screen.findByText(/Waiting for the AI model/)).toBeInTheDocument();
  });
});
