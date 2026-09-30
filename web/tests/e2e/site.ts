// What the tests share: the routes, the published data the pages are checked against, and a way to
// open a page as a reader would. The build under test points the API at the test server's mock,
// which refuses HEAD, answers its first request with a 503 and then serves the recorded session.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import type { Page } from "@playwright/test";

export const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "/lookahead";

const data = (name: string) => JSON.parse(readFileSync(fileURLToPath(new URL(`../../public/data/${name}`, import.meta.url)), "utf8"));

export interface ManifestFile {
  values: Record<string, { value: number | string | null; fmt: string }>;
  tables: Record<string, { columns: string[]; rows: (number | string | null)[][] }>;
}
export const manifest: ManifestFile = data("manifest.json");
export const bundle: {
  statement: string;
  served_backend: string;
  authorities: { authority: string; region: string }[];
  tiles: { authority: string }[];
  known_events: { event: string; node: string }[];
} = data("bundle.json");
export const recorded: { responses: Record<string, { body: { forecast_id?: string; unscored_share?: number } }> } = data("recorded_session.json");

export const FIRST_AUTHORITY = bundle.authorities[0]?.authority ?? "AECI";

// Every page the export writes, in navigation order, plus one authority page.
export const ROUTES = ["/", `/forecast/${FIRST_AUTHORITY}/`, "/backtest/", "/hierarchy/", "/events/", "/households/", "/report/"];

/** Open a route; the mock API is the only API the build can reach. */
export async function open(page: Page, route: string): Promise<void> {
  await page.route(
    (url) => url.hostname !== "127.0.0.1" && url.hostname !== "localhost",
    () => {
      // Never answered: no test can reach a live API by accident.
    },
  );
  await page.goto(`${BASE}${route}`);
}

/** Open a route with the mock API hanging too, the way a stopped machine behaves: the page must fall back to the recording. */
export async function openAsleep(page: Page, route: string): Promise<void> {
  await page.route(
    (url) => url.hostname !== "127.0.0.1" && url.hostname !== "localhost",
    () => {
      // Never answered.
    },
  );
  await page.route(
    (url) => url.pathname.startsWith("/mock-api/"),
    () => {
      // Never answered either: the six second probe gives up twice.
    },
  );
  await page.goto(`${BASE}${route}`);
}

/** The page sets data-ready on <html> once its first query over the marts has answered. */
export async function ready(page: Page): Promise<void> {
  await page.waitForFunction(() => document.documentElement.getAttribute("data-ready") === "true", null, { timeout: 60_000 });
}

/** Console errors and uncaught exceptions, collected from the moment this is called. */
/** The browser reports the first probe's 503 as a resource error; that answer is the API waking up
 * and the site handles it by probing again, so it is the one console line the check accepts. */
function isWakeUpProbe(text: string, url: string): boolean {
  return text.includes("status of 503") && /\/v1\/health$/.test(url);
}

export function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    if (isWakeUpProbe(msg.text(), msg.location().url)) return;
    errors.push(`${msg.text()} (${msg.location().url})`);
  });
  page.on("pageerror", (err) => errors.push(err.message));
  return errors;
}
