import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SectionShell } from "../components/sections/SectionShell";
import { makeAnalysis, makeRepo } from "../test/fixtures";
import { jsonResponse, mockFetch, renderWithProviders, sseResponse } from "../test/utils";
import { WorkspacePage } from "./WorkspacePage";

const mermaid = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn(async (id: string, _source: string) => ({
    svg: `<svg><g class="node" id="${id}-flowchart-m_core-1"><text>Core</text></g></svg>`,
  })),
}));
vi.mock("mermaid", () => ({ default: mermaid }));

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

const chatAnswer = {
  id: "a1",
  role: "assistant",
  content: "They live in UserService.",
  status: "complete",
  error: "",
  citations: [],
  tool_steps: [],
  created_at: "",
};

function mockBackend(analysis = makeAnalysis()) {
  const chatMessages: (typeof chatAnswer)[] = [];
  return mockFetch((url) => {
    if (url.endsWith("/api/auth/refresh")) return jsonResponse({ access: "a", user });
    if (url.endsWith("/analysis")) return jsonResponse(analysis);
    if (url.endsWith("/api/llm/health")) {
      return jsonResponse({ online: true, model: "m", latency_ms: 1, checked_at: "", error: null });
    }
    if (url.includes("/threads?")) {
      return jsonResponse({ count: 0, next: null, previous: null, results: [] });
    }
    if (url.endsWith("/threads")) {
      return jsonResponse({ id: "t1", title: "", created_at: "", updated_at: "" }, 201);
    }
    if (url.endsWith("/threads/t1")) {
      return jsonResponse({
        id: "t1",
        title: "",
        created_at: "",
        updated_at: "",
        messages: chatMessages,
      });
    }
    if (url.endsWith("/messages/stream")) {
      chatMessages.push(chatAnswer);
      return sseResponse([`event: done\ndata: ${JSON.stringify({ message: chatAnswer })}\n\n`]);
    }
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

  it("draws the architecture with strict Mermaid and highlights clicked modules", async () => {
    mockBackend();
    renderWorkspace("/repos/repo1?tab=architecture");

    const diagram = await screen.findByRole("img", { name: /Architecture diagram with 3 modules/ });
    expect(mermaid.initialize).toHaveBeenCalledWith(
      expect.objectContaining({ securityLevel: "strict", startOnLoad: false }),
    );
    expect(mermaid.render.mock.calls[0]?.[1]).toContain('m_app(["Application"])');
    expect(screen.getByText(/routes call an in-memory service/)).toBeInTheDocument();
    expect(screen.getByText(/registers routes/)).toBeInTheDocument();
    expect(screen.getByText("(1 import)")).toBeInTheDocument();

    const core = screen.getByRole("heading", { name: "Core" }).closest("li");
    expect(core).not.toHaveAttribute("aria-current");
    await userEvent.click(within(diagram).getByText("Core"));
    expect(core).toHaveAttribute("aria-current", "true");

    // Directory chips are not clickable; file chips open the viewer.
    expect(within(core as HTMLElement).getByRole("button", { name: /app\// })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /app\/main\.py/ }));
    expect(await screen.findByText("app/main.py line 30")).toBeInTheDocument();
  });

  it("asks an overview starter question in the chat panel", async () => {
    const fetchSpy = mockBackend();
    renderWorkspace();
    await userEvent.click(await screen.findByRole("button", { name: "Where are users stored?" }));

    const chat = await screen.findByRole("complementary", { name: "Chat" });
    expect(await within(chat).findByText("They live in UserService.")).toBeInTheDocument();
    const stream = fetchSpy.mock.calls.find(([url]) => String(url).endsWith("/messages/stream"));
    expect(JSON.parse(String(stream?.[1]?.body))).toEqual({ content: "Where are users stored?" });
  });

  it("lists tour stops and links into tour mode", async () => {
    mockBackend();
    renderWorkspace("/repos/repo1?tab=tour");

    const stops = within(await screen.findByRole("list", { name: "Tour stops" })).getAllByRole(
      "listitem",
    );
    expect(stops).toHaveLength(3);
    expect(stops[1]).toHaveTextContent("Flow trace");
    expect(screen.getByRole("link", { name: "Start the tour →" })).toHaveAttribute(
      "href",
      "/repos/repo1/tour",
    );
    expect(screen.getByRole("link", { name: "Service" })).toHaveAttribute(
      "href",
      "/repos/repo1/tour?step=3",
    );
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

describe("Re-analyze", () => {
  function withReanalyze(response: () => Response) {
    const spy = mockBackend();
    const backend = spy.getMockImplementation();
    spy.mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/reanalyze")) return response();
      return backend!(input, init);
    });
    return spy;
  }

  function start(id: string, created: boolean, cached: boolean) {
    return jsonResponse(
      { repository: makeRepo({ id }), job: null, created, cached },
      created ? 201 : 200,
    );
  }

  it("says when everything is already up to date", async () => {
    const spy = withReanalyze(() => start("repo1", false, true));
    renderWorkspace();
    await userEvent.click(await screen.findByRole("button", { name: "Re-analyze" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Already up to date");
    const call = spy.mock.calls.find(([url]) => String(url).endsWith("/reanalyze"));
    expect(call?.[1]?.method).toBe("POST");
  });

  it("re-runs unfinished sections in place", async () => {
    withReanalyze(() => start("repo1", true, false));
    const { router } = renderWorkspace();
    await userEvent.click(await screen.findByRole("button", { name: "Re-analyze" }));
    expect(await screen.findByText(/Re-running the AI sections/)).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/repos/repo1");
  });

  it("opens the progress page of a newer commit", async () => {
    withReanalyze(() => start("repo2", true, false));
    const { router } = renderWithProviders(<></>, {
      path: "/repos/repo1",
      routes: [
        { path: "/repos/:repoId", element: <WorkspacePage /> },
        { path: "/repos/:repoId/progress", element: <p>Progress page</p> },
      ],
      auth: true,
    });
    await userEvent.click(await screen.findByRole("button", { name: "Re-analyze" }));
    expect(await screen.findByText("Progress page")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/repos/repo2/progress");
  });

  it("shows rate-limit errors", async () => {
    withReanalyze(() =>
      jsonResponse(
        {
          error: {
            code: "rate_limited",
            message: "You can start 5 new analyses per hour. Try again in 12 minutes.",
            details: { retry_after_seconds: 700 },
          },
        },
        429,
      ),
    );
    renderWorkspace();
    await userEvent.click(await screen.findByRole("button", { name: "Re-analyze" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again in 12 minutes.");
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
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
