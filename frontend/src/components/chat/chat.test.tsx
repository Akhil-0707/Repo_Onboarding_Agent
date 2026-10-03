import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "../../api/chat";
import { jsonResponse, mockFetch, renderWithProviders, sseResponse } from "../../test/utils";
import { AnswerText } from "./AnswerText";
import { ChatPanel } from "./ChatPanel";

const thread = {
  id: "t1",
  title: "",
  created_at: "2026-10-02T00:00:00Z",
  updated_at: "2026-10-02T00:00:00Z",
};

function message(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: "m",
    role: "assistant",
    content: "",
    status: "complete",
    error: "",
    citations: [],
    tool_steps: [],
    created_at: "2026-10-02T00:00:00Z",
    ...overrides,
  };
}

const question = message({ id: "q1", role: "user", content: "Where are users stored?" });
const answer = message({
  id: "a1",
  content: "In memory, by **UserService** [app/services.py:10-20].",
  citations: [{ path: "app/services.py", start_line: 10, end_line: 20 }],
  tool_steps: [{ id: 1, name: "read_file", summary: "Reading 'app/services.py'", ok: true }],
});

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** A stateful fake backend: one thread whose messages grow as questions are answered. */
function mockChatBackend({
  online = true,
  stream = () =>
    sseResponse([
      sse("start", { message: question }),
      sse("tool_start", { id: 1, name: "read_file", summary: "Reading 'app/services.py'" }),
      sse("tool_end", answer.tool_steps[0]),
      sse("token", { text: "Let me look… " }),
      sse("retract", {}),
      sse("token", { text: "In memory" }),
      sse("citation", answer.citations[0]),
      sse("done", { message: answer }),
    ]),
}: { online?: boolean; stream?: () => Response } = {}) {
  const messages: ChatMessage[] = [];
  const threads: (typeof thread)[] = [];
  const calls: { url: string; method: string; body?: unknown }[] = [];
  const spy = mockFetch((url, init) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (url.endsWith("/api/llm/health")) {
      return jsonResponse({ online, model: "m", latency_ms: 1, checked_at: "", error: null });
    }
    if (url.endsWith("/messages/stream")) {
      const response = stream();
      if (response.ok) messages.push(question, answer);
      return response;
    }
    if (url.includes("/threads?")) {
      return jsonResponse({ count: threads.length, next: null, previous: null, results: threads });
    }
    if (url.endsWith("/threads") && method === "POST") {
      threads.push(thread);
      return jsonResponse(thread, 201);
    }
    if (url.endsWith("/threads/t1")) return jsonResponse({ ...thread, messages });
    return jsonResponse({}, 404);
  });
  return { spy, calls };
}

function renderPanel(props: Partial<Parameters<typeof ChatPanel>[0]> = {}) {
  const onOpen = vi.fn();
  renderWithProviders(
    <ChatPanel
      repoId="repo1"
      starterQuestions={["Where are users stored?", "How are routes registered?"]}
      onOpen={onOpen}
      {...props}
    />,
  );
  return { onOpen };
}

describe("ChatPanel", () => {
  it("asks a starter question, shows live steps and renders the cited answer", async () => {
    const { calls } = mockChatBackend();
    const { onOpen } = renderPanel();

    const suggestions = await screen.findByRole("list", { name: "Suggested questions" });
    await userEvent.click(within(suggestions).getByText("Where are users stored?"));

    expect(await screen.findByText("UserService")).toBeInTheDocument();
    expect(screen.getByText("Where are users stored?")).toBeInTheDocument();
    expect(screen.queryByText(/Let me look/)).not.toBeInTheDocument();
    expect(screen.getByText("1 research step")).toBeInTheDocument();

    const post = calls.find((c) => c.url.endsWith("/messages/stream"));
    expect(post?.url).toBe("/api/repos/repo1/threads/t1/messages/stream");
    expect(post?.body).toEqual({ content: "Where are users stored?" });
    expect(calls.some((c) => c.url.endsWith("/threads") && c.method === "POST")).toBe(true);

    await userEvent.click(screen.getByRole("button", { name: /app\/services\.py:10-20/ }));
    expect(onOpen).toHaveBeenCalledWith({
      path: "app/services.py",
      start_line: 10,
      end_line: 20,
    });
  });

  it("sends with Enter but not Shift+Enter", async () => {
    const { calls } = mockChatBackend();
    renderPanel();
    const input = await screen.findByLabelText("Ask a question");
    await userEvent.type(input, "First line{Shift>}{Enter}{/Shift}second");
    expect(calls.some((c) => c.url.endsWith("/messages/stream"))).toBe(false);
    await userEvent.type(input, "{Enter}");
    await screen.findByText("UserService");
    const post = calls.find((c) => c.url.endsWith("/messages/stream"));
    expect(post?.body).toEqual({ content: "First line\nsecond" });
    expect(input).toHaveValue("");
  });

  it("disables asking while the model is offline", async () => {
    mockChatBackend({ online: false });
    renderPanel();
    expect(await screen.findByText(/The AI model is offline/)).toBeInTheDocument();
    expect(screen.getByLabelText("Ask a question")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Where are users stored?" })).toBeDisabled();
  });

  it("shows a mid-answer failure", async () => {
    mockChatBackend({
      stream: () =>
        sseResponse([
          sse("start", { message: question }),
          sse("error", { code: "model_offline", message: "The model server went offline." }),
        ]),
    });
    renderPanel();
    await userEvent.type(await screen.findByLabelText("Ask a question"), "Hi?{Enter}");
    expect(await screen.findByText("The model server went offline.")).toBeInTheDocument();
    expect(screen.getByLabelText("Ask a question")).toHaveValue("");
  });

  it("gives the question back when it was rejected before streaming", async () => {
    mockChatBackend({
      stream: () =>
        jsonResponse(
          { error: { code: "model_offline", message: "The AI model is offline." } },
          503,
        ),
    });
    renderPanel();
    await userEvent.type(await screen.findByLabelText("Ask a question"), "Hi?{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("The AI model is offline.");
    await waitFor(() => expect(screen.getByLabelText("Ask a question")).toHaveValue("Hi?"));
  });

  it("asks an external question once on mount", async () => {
    const { calls } = mockChatBackend();
    renderPanel({ autoAsk: "How are routes registered?" });
    await screen.findByText("UserService");
    const posts = calls.filter((c) => c.url.endsWith("/messages/stream"));
    expect(posts).toHaveLength(1);
    expect(posts[0]?.body).toEqual({ content: "How are routes registered?" });
  });
});

describe("AnswerText", () => {
  it("renders a safe Markdown subset with clickable validated citations only", async () => {
    const onOpen = vi.fn();
    renderWithProviders(
      <AnswerText
        text={
          "Intro with `code` and [app/main.py:8-11] but not [ghost.py:1-2].\n\n" +
          "- one\n- two\n\n```js\nconst x = '[app/main.py:8-11]';\n```\n\n<b>raw</b>"
        }
        citations={[{ path: "app/main.py", start_line: 8, end_line: 11 }]}
        onOpen={onOpen}
      />,
    );
    expect(screen.getAllByRole("button")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: /app\/main\.py:8-11/ }));
    expect(onOpen).toHaveBeenCalledWith({ path: "app/main.py", start_line: 8, end_line: 11 });
    expect(screen.getByText(/\[ghost\.py:1-2\]/)).toBeInTheDocument();
    expect(screen.getByText("code").tagName).toBe("CODE");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("const x = '[app/main.py:8-11]';").tagName).toBe("CODE");
    expect(screen.getByText("<b>raw</b>")).toBeInTheDocument(); // never parsed as HTML
  });

  it("keeps the numbering of list items separated by blank lines", () => {
    renderWithProviders(
      <AnswerText text={"1. first\n\n2. second\n\n3. third"} citations={[]} onOpen={vi.fn()} />,
    );
    const starts = screen.getAllByRole("list").map((list) => list.getAttribute("start"));
    expect(starts).toEqual(["1", "2", "3"]);
  });
});
