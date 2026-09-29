import { expect, test } from "@playwright/test";

import { open, ready, ROUTES } from "./site";

// At phone width no page may scroll sideways; the tile map scrolls inside its own region.
for (const route of ROUTES) {
  test(`${route} has no horizontal page scroll at phone width`, async ({ page }) => {
    await open(page, route);
    await ready(page);
    await page.waitForTimeout(500);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}

test("the tile map scrolls sideways inside its own region on a phone", async ({ page }) => {
  await open(page, "/");
  await ready(page);
  const scroller = page.getByTestId("tile-map").locator(".overflow-x-auto");
  const wider = await scroller.evaluate((el) => el.scrollWidth > el.clientWidth);
  expect(wider).toBe(true);
});
