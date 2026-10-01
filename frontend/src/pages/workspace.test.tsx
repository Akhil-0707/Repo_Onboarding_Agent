import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SectionShell } from "../components/sections/SectionShell";
import { makeAnalysis, makeRepo } from "../test/fixtures";
import { jsonResponse, mockFetch, renderWithProviders } from "../test/utils";
import { WorkspacePage } from "./WorkspacePage";

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

function mockBackend(analysis = makeAnalysis()) {
  return mockFetch((url) => {
    if (url.endsWith("/api/auth/refresh")) return jsonResponse({ access: "a", user });
    if (url.endsWith("/analysis")) return jsonResponse(analysis);
    if (url.endsWith("/tree")) {
      return jsonResponse({
        commit_sha: "abc",
        files: ["app/main.py", "app/services.py", "README.md"].map((path) => ({
          path,
          language: "python",
          size: 10,
          lines: 30,
        })),
      });
    }
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

function renderWorkspace(path = "/repos/repo1") {
  return renderWithProviders(<></>, {
    path,
    routes: [{ path: "/repos/:repoId", element: <WorkspacePage /> }],
    auth: true,
  });
}

describe("WorkspacePage", () => {
  it("shows the AI overview and opens cited lines in the code viewer", async () => {
    mockBackend();
    const { router } = renderWorkspace();

    expect(await screen.findByText(/tiny Flask service/)).toBeInTheDocument();
    expect(screen.getByText("HTTP framework")).toBeInTheDocument();
    expect(screen.getByText("pip install -e .")).toBeInTheDocument();
    expect(screen.getByText("Repository facts")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /app\/main\.py:8-11/ }));
    expect(router.state.location.search).toBe("?file=app%2Fmain.py&lines=8-11");
    expect(await screen.findByText("app/main.py line 30")).toBeInTheDocument();
    const highlighted = [...document.querySelectorAll("[data-highlighted]")];
    expect(highlighted.map((el) => el.getAttribute("data-line"))).toEqual(["8", "9", "10", "11"]);
  });

  it("lists the start-here files in order and filters the glossary", async () => {
    mockBackend();
    renderWorkspace("/repos/repo1?tab=start-here");

    const list = await screen.findByRole("list", { name: "Reading list" });
    const items = within(list).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("app/main.py");
    expect(items[1]).toHaveTextContent("app/services.py:10-21");

    await userEvent.click(screen.getByRole("tab", { name: "Glossary" }));
    expect(await screen.findByText("UserService")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Filter glossary"), "environment");
    expect(screen.queryByText("UserService")).not.toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("explains that the analysis is waiting for the model", async () => {
    const waiting = makeAnalysis({ status: "waiting_for_model" });
    waiting.sections.overview = { status: "pending", error: "", updated_at: null, data: null };
    mockBackend(waiting);
    renderWorkspace();
    expect(await screen.findByText("Waiting for the AI model")).toBeInTheDocument();
    expect(screen.getByText("Repository facts")).toBeInTheDocument();
  });
});

describe("SectionShell", () => {
  it("shows failures with the error message", async () => {
    renderWithProviders(
      <SectionShell
        title="Glossary"
        section={{ status: "failed", error: "Model returned junk", updated_at: null, data: null }}
        analysisStatus="partial"
      >
        {() => null}
      </SectionShell>,
    );
    expect(await screen.findByText("Glossary could not be generated")).toBeInTheDocument();
    expect(screen.getByText("Model returned junk")).toBeInTheDocument();
  });

  it("shows progress while the section is being written", async () => {
    renderWithProviders(
      <SectionShell
        title="Overview"
        section={{ status: "running", error: "", updated_at: null, data: null }}
        analysisStatus="running"
      >
        {() => null}
      </SectionShell>,
    );
    expect(await screen.findByText("Writing the overview…")).toBeInTheDocument();
  });
});
