import { expect, test } from "@playwright/test";

import { FakeApi } from "./fakeApi";

test("analyse a repository, explore it, take the tour and ask a question", async ({ page }) => {
  const api = new FakeApi();
  await api.install(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  // Landing → dashboard → start the analysis.
  await page.goto("/");
  await page.getByPlaceholder("https://github.com/owner/repo").fill("acme/tool");
  await page.getByRole("button", { name: "Analyze" }).click();
  await expect(page).toHaveURL(/\/dashboard\?analyze=acme%2Ftool/);
  await page.locator("form").getByRole("button").click();

  // Live progress, then the workspace opens by itself.
  await expect(page).toHaveURL(/\/repos\/repo1\/progress$/);
  await expect(page.getByText("Parsed 4 files")).toBeVisible();
  await expect(page.getByText("Finished, opening workspace…")).toBeVisible();
  await expect(page).toHaveURL(/\/repos\/repo1$/, { timeout: 10_000 });

  // Overview with a citation that opens the code viewer at the cited lines.
  await expect(page.getByText(/tiny Flask service/)).toBeVisible();
  await page.getByRole("button", { name: /app\/main\.py:8-11/ }).click();
  await expect(page).toHaveURL(/file=app%2Fmain\.py&lines=8-11/);
  await expect(page.locator("[data-highlighted]")).toHaveCount(4);
  await page.getByRole("button", { name: "Close code viewer" }).click();

  // Architecture: Mermaid really renders in the browser (strict mode) into an SVG.
  await page.getByRole("tab", { name: "Architecture" }).click();
  const diagram = page.getByRole("img", { name: /Architecture diagram with 3 modules/ });
  await expect(diagram.locator("svg g.node")).toHaveCount(2);
  await diagram.locator("g.node", { hasText: "Core" }).click();
  await expect(page.locator("#module-core")).toHaveAttribute("aria-current", "true");

  // Guided tour in tour mode, driven with the keyboard.
  await page.getByRole("tab", { name: "Tour" }).click();
  await page.getByRole("link", { name: "Start the tour →" }).click();
  await expect(page.getByRole("heading", { name: "Start-up" })).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("heading", { name: "Routing" })).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Tour progress" })).toHaveAttribute(
    "aria-valuenow",
    "2",
  );
  await page.keyboard.press("ArrowRight");
  await page.getByRole("link", { name: "Finish" }).click();
  await expect(page).toHaveURL(/\/repos\/repo1\?tab=tour$/);

  // Chat: a streamed, cited answer.
  await page.getByRole("button", { name: "Ask a question" }).click();
  const chat = page.getByRole("complementary", { name: "Chat" });
  await chat.getByLabel("Ask a question").fill("Where are users stored?");
  await chat.getByLabel("Ask a question").press("Enter");
  await expect(chat.getByText("UserService")).toBeVisible();
  await expect(chat.getByText("1 research step")).toBeVisible();
  await chat.getByRole("button", { name: /app\/services\.py:10-20/ }).click();
  await expect(page).toHaveURL(/file=app%2Fservices\.py&lines=10-20/);
  expect(api.questions).toEqual(["Where are users stored?"]);

  // The repository is on the dashboard.
  await page.getByRole("link", { name: "Dashboard" }).first().click();
  await expect(page.getByRole("region", { name: "Analyzed repositories" })).toContainText(
    "acme/tool",
  );

  expect(api.unexpected).toEqual([]);
  expect(errors).toEqual([]);
});

test("the chat is disabled while the model server is offline", async ({ page }) => {
  const api = new FakeApi();
  api.repoStatus = "ready";
  await api.install(page);
  await page.route("**/api/llm/health", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        online: false,
        model: "Qwen/Qwen3-8B",
        latency_ms: null,
        checked_at: "2026-10-03T00:00:00Z",
        error: "unreachable",
      }),
    }),
  );

  await page.goto("/repos/repo1");
  await page.getByRole("button", { name: "Ask a question" }).click();
  const chat = page.getByRole("complementary", { name: "Chat" });
  await expect(chat.getByText(/The AI model is offline/)).toBeVisible();
  await expect(chat.getByLabel("Ask a question")).toBeDisabled();
});
