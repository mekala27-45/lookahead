import { expect, test } from "@playwright/test";

import { formatValue } from "../../src/lib/format";

import { BASE, bundle, collectErrors, FIRST_AUTHORITY, manifest, open, openAsleep, ready, recorded, ROUTES } from "./site";

const printed = (key: string) => {
  const entry = manifest.values[key];
  if (!entry) throw new Error(`the manifest has no ${key}`);
  return formatValue(entry.value, entry.fmt);
};
const served = bundle.served_backend;

test("the control room shows the two headline numbers, the coverage and the statement", async ({ page }) => {
  await open(page, "/");
  await expect(page.getByTestId("headline-wins-value")).toContainText(printed(`skill.${served}.h1_24.wins`));
  await expect(page.getByTestId("headline-losses-value")).toContainText(printed(`skill.${served}.h1_24.losses`));
  await expect(page.getByTestId("headline-coverage-value")).toHaveText(printed(`backtest.${served}.coverage_90`));
  await expect(page.getByTestId("footer")).toContainText(bundle.statement);
});

test("the tile map renders every authority as a link, colored once the mart has answered", async ({ page }) => {
  await open(page, "/");
  await ready(page);
  const map = page.getByTestId("tile-map");
  await expect(map.locator("[data-authority]")).toHaveCount(bundle.tiles.length);
  await expect(map.locator("[data-authority][data-step]").first()).toBeVisible();
  for (const tile of bundle.tiles.slice(0, 5)) {
    await expect(map.locator(`[data-authority="${tile.authority}"]`)).toHaveAttribute("href", `${BASE}/forecast/${tile.authority}/`);
  }
});

test("the authority page draws the fan chart with its bands, the operator's line and the origin rule", async ({ page }) => {
  await open(page, `/forecast/${FIRST_AUTHORITY}/`);
  await ready(page);
  const fan = page.getByTestId("authority-fan");
  const legend = fan.getByRole("list", { name: "Legend" });
  await expect(legend.locator('[data-legend-item="90% band"]')).toBeVisible();
  await expect(legend.locator('[data-legend-item="50% band"]')).toBeVisible();
  await expect(legend.locator("[data-legend-item=\"Operator's day ahead forecast\"]")).toBeVisible();
  await expect(legend.locator('[data-legend-item="Actual"]')).toBeVisible();
  await expect(fan.locator("svg[role='img'] path").first()).toBeVisible();
  await expect(fan.locator("[data-vrule]").first()).toBeVisible();
});

test("issuing a forecast through the site shows the id; the mock API's first 503 is survived by the second probe", async ({ page }) => {
  await open(page, `/forecast/${FIRST_AUTHORITY}/`);
  await ready(page);
  const source = page.getByTestId("issue-source");
  await expect(source).toHaveText("live API", { timeout: 30_000 });
  await page.getByTestId("write-token").fill("test-token");
  await page.getByTestId("issue-button").click();
  const issued = recorded.responses[`issue_${FIRST_AUTHORITY}`]?.body;
  await expect(page.getByTestId("forecast-id")).toHaveText(issued?.forecast_id ?? /^[0-9a-f-]{36}$/);
  await expect(page.getByTestId("issued")).toContainText("(live)");
});

test("with the API asleep the authority page issues from the recorded session and says so", async ({ page }) => {
  await openAsleep(page, `/forecast/${FIRST_AUTHORITY}/`);
  await ready(page);
  await expect(page.getByTestId("issue-source")).toHaveText("recorded session (API asleep)", { timeout: 40_000 });
  await page.getByTestId("issue-button").click();
  const issued = recorded.responses[`issue_${FIRST_AUTHORITY}`]?.body;
  await expect(page.getByTestId("forecast-id")).toHaveText(issued?.forecast_id ?? /^[0-9a-f-]{36}$/);
  await expect(page.getByTestId("issued")).toContainText("recorded session");
});

test("the control room's scorecard reports the unscored share from the recorded session when the API is asleep", async ({ page }) => {
  await openAsleep(page, "/");
  await expect(page.getByTestId("scorecard-source")).toHaveText("recorded session (API asleep)", { timeout: 40_000 });
  const share = recorded.responses.scorecard?.body.unscored_share;
  if (typeof share === "number") await expect(page.getByTestId("unscored-share")).toHaveText(formatValue(share, "pct1"));
});

test("the backtest tables' toggles show tables and the band toggle changes the skill forest", async ({ page }) => {
  await open(page, "/backtest/");
  await ready(page);
  const forest = page.getByTestId("skill-forest");
  const toggle = forest.getByTestId("table-toggle");
  await expect(forest.locator("table")).toHaveCount(0);
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await expect(forest.locator("table tbody tr").first()).toBeVisible();
  const rowsBefore = await forest.locator("table tbody tr").count();
  expect(rowsBefore).toBeGreaterThan(5);
  await page.getByTestId("band-toggle").getByRole("button", { name: "The target day" }).click();
  await expect(forest).toContainText("the target day");
  await expect(page.getByTestId("by-horizon").locator("table tbody tr")).toHaveCount(48);
});

test("the events heatmap renders and the alerts carry a class word", async ({ page }) => {
  await open(page, "/events/");
  await ready(page);
  const heat = page.getByTestId("residual-heatmap");
  await expect(heat.locator("svg[role='img'] rect").first()).toBeVisible();
  const list = page.getByTestId("alerts-list");
  await expect(list).toBeVisible();
  const statuses = list.locator("[data-status]");
  if ((await statuses.count()) > 0) await expect(statuses.first()).toHaveText(/demand event|data defect/);
});

for (const route of ROUTES) {
  test(`${route} carries the statement and the pushback, with no console errors`, async ({ page }) => {
    const errors = collectErrors(page);
    await open(page, route);
    await expect(page.getByTestId("footer")).toContainText(bundle.statement);
    await expect(page.getByRole("heading", { name: "What the operator would push back on" })).toBeVisible();
    await ready(page);
    await page.waitForLoadState("networkidle");
    expect(errors).toEqual([]);
  });
}

test("the theme is dark first, the toggle switches it and the choice is remembered", async ({ page }) => {
  await open(page, "/");
  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-theme", "dark");
  await page.getByTestId("theme-toggle").click();
  await expect(html).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "light");
});

test("the report page defaults to the light theme and prints", async ({ page }) => {
  await open(page, "/report/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByTestId("memo")).toContainText("Skill against the operator");
  await expect(page.getByTestId("print")).toBeVisible();
});

test("a client that sends HEAD is refused by the test server, as by the host", async ({ request }) => {
  const response = await request.head(`${BASE}/data/bundle.json`);
  expect(response.status()).toBe(405);
  const get = await request.get(`${BASE}/data/bundle.json`);
  expect(get.status()).toBe(200);
});
