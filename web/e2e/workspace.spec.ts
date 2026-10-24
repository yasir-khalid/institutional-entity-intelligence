import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const LEI = "254900TESTENTITY00001";

test("saved investigation reload, follow-up, rename and evidence", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page
    .getByLabel("Research question", { exact: true })
    .fill(`Who is Acme? ${testInfo.project.name}`);
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(page).toHaveURL(/\/research\//);
  await expect(
    page.getByText("Research answer", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("Research answer", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Sources & addressed facts" }),
  ).toBeVisible();
  await page.getByLabel("Ask a follow-up").fill("And its registration?");
  await page.getByRole("button", { name: "Send follow-up" }).click();
  await expect(page.getByText("Research answer", { exact: true })).toHaveCount(
    2,
  );
  await page.getByRole("combobox", { name: "Sources for answer" }).click();
  await page.getByRole("option", { name: `1. Who is Acme? ${testInfo.project.name}`, exact: true }).click();
  await expect(
    page.locator(".investigation-evidence .fact-row strong").filter({ hasText: /^US$/ }),
  ).toBeVisible();
  await page.getByRole("combobox", { name: "Sources for answer" }).click();
  await page.getByRole("option", { name: "2. And its registration?", exact: true }).click();
  await expect(
    page.locator(".investigation-evidence .fact-row strong").filter({ hasText: /^US$/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Rename investigation" }).click();
  await page
    .getByLabel("Investigation title")
    .fill(`Acme dossier ${testInfo.project.name}`);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: `Acme dossier ${testInfo.project.name}`,
    }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", {
      name: `Acme dossier ${testInfo.project.name}`,
    }),
  ).toBeVisible();
  const turns = page
    .getByRole("region", { name: "Research conversation" })
    .getByRole("article");
  const firstTurn = await turns.nth(0).boundingBox();
  const secondTurn = await turns.nth(1).boundingBox();
  expect(secondTurn!.y).toBeGreaterThanOrEqual(
    firstTurn!.y + firstTurn!.height,
  );
  const accessibility = await new AxeBuilder({ page })
    .include("#workspace-main")
    .analyze();
  expect(accessibility.violations).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath("research.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("shareable entity tabs, immutable reviews, coverage and navigation", async ({
  page,
}, testInfo) => {
  await page.goto(`/entities?q=${LEI}&type=lei`);
  await page
    .getByRole("link", { name: "Open shareable entity profile" })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Acme Capital Management",
  );
  await page.getByRole("tab", { name: "Reported activity" }).click();
  await expect(page).toHaveURL(/tab=holdings/);
  await page.reload();
  await expect(
    page.getByRole("tab", { name: "Reported activity" }),
  ).toHaveAttribute("data-state", "active");
  await expect(
    page.getByText("Latest reported 13F holdings", { exact: true }),
  ).toBeVisible();
  expect(
    (await new AxeBuilder({ page }).include("#workspace-main").analyze())
      .violations,
  ).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath("entity.png"),
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Relationships", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "GLEIF accounting hierarchy" }),
  ).toBeVisible();
  await page.goto("/reviews");
  await page
    .getByLabel("Reviewer", { exact: true })
    .fill(`Analyst ${testInfo.project.name}`);
  await page
    .getByLabel("Rationale", { exact: true })
    .fill("Confirmed against the source record.");
  await page.getByRole("button", { name: "Confirm link", exact: true }).click();
  await expect(
    page.getByText(`latest: confirmed by Analyst ${testInfo.project.name}`, {
      exact: false,
    }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText(`Analyst ${testInfo.project.name}`, { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("REVIEW", { exact: true })).toBeVisible();
  expect(
    (await new AxeBuilder({ page }).include("#workspace-main").analyze())
      .violations,
  ).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath("reviews.png"),
    fullPage: true,
  });
  await page.goto("/coverage");
  await expect(
    page.getByRole("heading", { name: "GLEIF LEI", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("2026-06-30", { exact: false }).first(),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Search & navigate", exact: false })
    .click();
  await page
    .getByPlaceholder("Search pages, investigations, or entities…")
    .fill("Entities");
  await page.getByRole("option", { name: "Entities", exact: true }).click();
  await expect(page).toHaveURL(/\/entities$/);
  if (testInfo.project.name === "mobile") {
    await page
      .getByRole("button", { name: "Toggle Sidebar", exact: true })
      .click();
    await page
      .getByRole("link", { name: "Data coverage", exact: true })
      .click();
    await expect(page).toHaveURL(/\/coverage$/);
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }
  const accessibility = await new AxeBuilder({ page })
    .include("#workspace-main")
    .analyze();
  expect(accessibility.violations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
  ).toBe(false);
  await page.screenshot({
    path: testInfo.outputPath("workspace.png"),
    fullPage: true,
  });
});

test("failed and stopped research can be resumed", async ({ page }) => {
  await page.goto("/");
  await page
    .getByLabel("Research question", { exact: true })
    .fill("Fixture failure question");
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(
    page.getByText("Fixture provider unavailable", { exact: true }),
  ).toBeVisible();
  const retry = page.waitForResponse(
    (response) =>
      response.url().endsWith("/retry") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Retry question", exact: true })
    .click();
  expect((await retry).status()).toBe(202);
  await expect(
    page.getByText("Fixture provider unavailable", { exact: true }),
  ).toBeVisible();
  await page.goto("/");
  await page
    .getByLabel("Research question", { exact: true })
    .fill("A slow research question");
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Stop research", exact: true })
    .click();
  await expect(
    page.getByText("Research stopped. Previous answers are unchanged.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Retry question", exact: true }),
  ).toBeVisible();
});
