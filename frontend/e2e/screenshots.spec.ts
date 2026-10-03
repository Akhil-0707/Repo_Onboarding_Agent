/**
 * Regenerates the README screenshots from a real analysis, replayed in the real UI.
 *
 *   docker compose exec backend python manage.py export_snapshot <user> <owner/name> --out /tmp/s.json
 *   docker compose cp backend:/tmp/s.json test-results/snapshot.json
 *   SNAPSHOT=test-results/snapshot.json npm run screenshots
 *
 * Skipped unless SNAPSHOT is set, so the normal E2E run ignores it.
 */
import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

interface Snapshot {
  repo_id: string;
  responses: Record<string, unknown>;
}

const SNAPSHOT = process.env.SNAPSHOT;
const OUT = "../docs/screenshots";

test.skip(!SNAPSHOT, "Set SNAPSHOT to a file written by `manage.py export_snapshot`.");
test.describe.configure({ mode: "serial" });
test.use({ viewport: { width: 1440, height: 900 }, colorScheme: "light" });

function load(): Snapshot {
  return JSON.parse(readFileSync(SNAPSHOT ?? "", "utf-8")) as Snapshot;
}

function key(url: URL): string {
  const path = url.searchParams.get("path");
  return path === null ? url.pathname : `${url.pathname}?${new URLSearchParams({ path })}`;
}

async function replay(page: Page, snapshot: Snapshot, overrides: Record<string, unknown> = {}) {
  const analysis = snapshot.responses[`/api/repos/${snapshot.repo_id}/analysis`] as {
    model: string;
  };
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url());
    const fixed: Record<string, unknown> = {
      "/api/auth/refresh": {
        access: "screenshot-token",
        user: {
          id: "u1", username: "dev", name: "Dev", email: "", avatar_url: "",
          github_connected: true, private_repo_access: false,
          date_joined: "2026-10-01T00:00:00Z",
        },
      }, // prettier-ignore
      "/api/llm/health": {
        online: true, model: analysis.model, latency_ms: 38,
        checked_at: "2026-10-03T00:00:00Z", error: null,
      }, // prettier-ignore
      ...overrides,
    };
    const body = fixed[url.pathname] ?? snapshot.responses[key(url)];
    if (body === undefined) {
      return route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "not_found", message: key(url), details: null } }),
      });
    }
    return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function shoot(page: Page, name: string) {
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: `${OUT}/${name}.png` });
}

test("dashboard", async ({ page }) => {
  const snapshot = load();
  await replay(page, snapshot);
  await page.goto("/dashboard");
  await expect(page.getByRole("region", { name: "Analyzed repositories" })).toContainText(
    "commander",
  );
  await shoot(page, "dashboard");
});

test("progress", async ({ page }) => {
  const snapshot = load();
  const base = `/api/repos/${snapshot.repo_id}`;
  const repo = snapshot.responses[base] as Record<string, unknown>;
  const job = structuredClone(snapshot.responses[`${base}/job`]) as {
    status: string;
    progress: number;
    steps: { key: string; status: string; progress: number; message: string }[];
  };
  // Show the real job as it looked mid-run: indexed, embedding in progress.
  const order = job.steps.map((s) => s.key);
  const current = order.indexOf("embed");
  job.steps.forEach((step, index) => {
    if (index === current) Object.assign(step, { status: "running", progress: 64, message: "" });
    if (index > current) Object.assign(step, { status: "pending", progress: 0, message: "" });
  });
  Object.assign(job, { status: "running", progress: 58 });
  await replay(page, snapshot, { [base]: { ...repo, status: "ingesting" } });
  const events = `event: snapshot\ndata: ${JSON.stringify(job)}\n\n`;
  await page.addInitScript((text) => {
    const original = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (!url.endsWith("/job/stream")) return original(input, init);
      // A stream that stays open, like a live job.
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(new TextEncoder().encode(text));
        },
      });
      return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
    };
  }, events);
  await page.goto(`/repos/${snapshot.repo_id}/progress`);
  await expect(page.getByRole("list", { name: "Ingestion steps" })).toBeVisible();
  await page.screenshot({ path: `${OUT}/progress.png` });
});

test("workspace overview", async ({ page }) => {
  const snapshot = load();
  await replay(page, snapshot);
  await page.goto(`/repos/${snapshot.repo_id}`);
  await expect(page.getByRole("heading", { name: "Questions to ask" })).toBeVisible();
  await shoot(page, "workspace");
});

test("architecture", async ({ page }) => {
  const snapshot = load();
  await replay(page, snapshot);
  await page.goto(`/repos/${snapshot.repo_id}?tab=architecture`);
  await expect(
    page.getByRole("img", { name: /Architecture diagram/ }).locator("svg"),
  ).toBeVisible();
  await shoot(page, "architecture");
});

test("tour", async ({ page }) => {
  const snapshot = load();
  await replay(page, snapshot);
  await page.goto(`/repos/${snapshot.repo_id}/tour?step=6`);
  await expect(page.getByRole("progressbar", { name: "Tour progress" })).toBeVisible();
  await expect(page.locator("[data-highlighted]").first()).toBeVisible();
  await shoot(page, "tour");
});

test("chat", async ({ page }) => {
  const snapshot = load();
  await replay(page, snapshot);
  await page.goto(`/repos/${snapshot.repo_id}`);
  await page.getByRole("button", { name: "Ask a question" }).click();
  const chat = page.getByRole("complementary", { name: "Chat" });
  const citation = chat.getByRole("button", { name: /lib\/option\.js/ }).first();
  await citation.click();
  await expect(page.locator("[data-highlighted]").first()).toBeVisible();
  await shoot(page, "chat");
});
