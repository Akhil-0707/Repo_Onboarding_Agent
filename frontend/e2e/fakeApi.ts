import type { Page, Route } from "@playwright/test";

import { makeAnalysis, makeJob, makeRepo, makeStep } from "../src/test/fixtures";

const REPO_ID = "repo1";
const FILES = ["app/main.py", "app/routes.py", "app/services.py", "README.md"];

function sse(events: [string, unknown][]): string {
  return events
    .map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
    .join("");
}

/**
 * A stateful in-browser fake of the RepoGuide API: a signed-in user analyses one repository,
 * watches it ingest, then explores it and chats about it.
 */
export class FakeApi {
  repoStatus: "none" | "queued" | "ready" = "none";
  threads: { id: string; title: string; created_at: string; updated_at: string }[] = [];
  messages: unknown[] = [];
  questions: string[] = [];
  unexpected: string[] = [];

  async install(page: Page): Promise<void> {
    await page.route("**/api/**", (route) => this.handle(route));
  }

  private repo() {
    return makeRepo({ id: REPO_ID, status: this.repoStatus === "ready" ? "ready" : "queued" });
  }

  private json(route: Route, body: unknown, status = 200) {
    return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  }

  private stream(route: Route, events: [string, unknown][]) {
    return route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
      body: sse(events),
    });
  }

  private async handle(route: Route): Promise<void> {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const base = `/api/repos/${REPO_ID}`;

    if (path === "/api/auth/refresh") {
      return this.json(route, {
        access: "e2e-access-token",
        user: {
          id: "u1", username: "octo", name: "Octo Cat", email: "", avatar_url: "",
          github_connected: true, private_repo_access: false,
          date_joined: "2026-10-01T00:00:00Z",
        },
      }); // prettier-ignore
    }
    if (path === "/api/llm/health") {
      return this.json(route, {
        online: true, model: "Qwen/Qwen3-8B", latency_ms: 42,
        checked_at: "2026-10-03T00:00:00Z", error: null,
      }); // prettier-ignore
    }
    if (path === "/api/repos" && method === "POST") {
      this.repoStatus = "queued";
      return this.json(
        route,
        { repository: this.repo(), job: makeJob(), created: true, cached: false },
        201,
      );
    }
    if (path === "/api/repos") {
      const results = this.repoStatus === "none" ? [] : [this.repo()];
      return this.json(route, { count: results.length, next: null, previous: null, results });
    }
    if (path === base) return this.json(route, this.repo());
    if (path === `${base}/job/stream`) {
      const running = makeJob({ status: "running", progress: 40 });
      this.repoStatus = "ready"; // indexing finishes during this stream
      return this.stream(route, [
        ["snapshot", running],
        ["step", { type: "step", key: "parse", status: "done", message: "Parsed 4 files", job_progress: 70 }],
        ["log", { type: "log", key: "embed", ts: "2026-10-03T00:00:01Z", level: "info", message: "Embedded 12 chunks" }],
        ["snapshot", makeJob({ status: "done", progress: 100, steps: [
          makeStep({ key: "clone", label: "Clone repository", status: "done", progress: 100 }),
          makeStep({ key: "parse", label: "Parse code", status: "done", progress: 100, message: "Parsed 4 files" }),
        ] })],
        ["end", { status: "done" }],
      ]); // prettier-ignore
    }
    if (path === `${base}/analysis`) return this.json(route, makeAnalysis());
    if (path === `${base}/tree`) {
      return this.json(route, {
        commit_sha: "abc",
        files: FILES.map((file) => ({ path: file, language: "python", size: 100, lines: 30 })),
      });
    }
    if (path === `${base}/files`) {
      const file = url.searchParams.get("path") ?? "";
      return this.json(route, {
        path: file, language: "python", size: 100, lines: 30, start_line: 1, end_line: 30,
        content: Array.from({ length: 30 }, (_, i) => `# ${file} line ${i + 1}`).join("\n"),
        symbols: [], github_url: `https://github.com/acme/tool/blob/abc/${file}`,
      }); // prettier-ignore
    }
    if (path === `${base}/threads` && method === "POST") {
      const thread = { id: "t1", title: "", created_at: "", updated_at: "" };
      this.threads = [thread];
      return this.json(route, thread, 201);
    }
    if (path === `${base}/threads`) {
      return this.json(route, {
        count: this.threads.length, next: null, previous: null, results: this.threads,
      }); // prettier-ignore
    }
    if (path === `${base}/threads/t1`) {
      return this.json(route, { ...this.threads[0], messages: this.messages });
    }
    if (path === `${base}/threads/t1/messages/stream` && method === "POST") {
      const content = String((request.postDataJSON() as { content: string }).content);
      this.questions.push(content);
      const question = { id: `q${this.questions.length}`, role: "user", content, status: "complete",
        error: "", citations: [], tool_steps: [], created_at: "" }; // prettier-ignore
      const answer = {
        id: `a${this.questions.length}`, role: "assistant", status: "complete", error: "",
        content: "Users live in memory inside **UserService** [app/services.py:10-20].",
        citations: [{ path: "app/services.py", start_line: 10, end_line: 20 }],
        tool_steps: [{ id: 1, name: "search_code", summary: "Searching for 'users'", ok: true, duration_ms: 12 }],
        created_at: "",
      }; // prettier-ignore
      this.messages.push(question, answer);
      return this.stream(route, [
        ["start", { message: question }],
        ["tool_start", { id: 1, name: "search_code", summary: "Searching for 'users'" }],
        ["tool_end", answer.tool_steps[0]],
        ["token", { text: "Users live in memory" }],
        ["citation", answer.citations[0]],
        ["done", { message: answer }],
      ]);
    }
    this.unexpected.push(`${method} ${path}`);
    return this.json(
      route,
      { error: { code: "not_found", message: "Not mocked", details: null } },
      404,
    );
  }
}
