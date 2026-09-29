// Build time readers for the committed bundle in public/data. Server components call these while
// the static export renders; nothing here ships to the browser.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { type Manifest, ManifestView } from "./manifest";

const DATA = join(process.cwd(), "public", "data");

function readJson<T>(name: string): T {
  return JSON.parse(readFileSync(join(DATA, name), "utf8")) as T;
}

let cached: ManifestView | null = null;
export function manifest(): ManifestView {
  if (!cached) cached = new ManifestView(readJson<Manifest>("manifest.json"));
  return cached;
}

export interface AuthorityInfo {
  authority: string;
  region: string;
  label: string;
  interconnection: string;
  comparable: boolean;
  typical_mw: number;
}
export interface RegionInfo {
  code: string;
  label: string;
  interconnection: string;
}
export interface Tile {
  authority: string;
  region: string;
  row: number;
  col: number;
}
export interface Bundle {
  statement: string;
  as_of: string;
  served_backend: string;
  backends: string[];
  authorities: AuthorityInfo[];
  regions: RegionInfo[];
  tiles: Tile[];
  policy: Record<string, number | string>;
  files: string[];
  bytes: Record<string, number>;
  known_events: { event: string; node: string; onset_utc: string; end_utc: string; description: string }[];
}

let bundleCache: Bundle | null = null;
export function bundle(): Bundle {
  if (!bundleCache) bundleCache = readJson<Bundle>("bundle.json");
  return bundleCache;
}

export interface LiveCheck {
  checked_at: string;
  browser: string;
  pages: { route: string; loaded: boolean; statement: boolean; note: string }[];
  api_awake: { health: string; forecast_id: string | null };
  api_asleep: { recorded_session_used: boolean; note: string };
  passed: boolean;
}

export function liveCheck(): LiveCheck | null {
  try {
    return readJson<LiveCheck>("live_check.json");
  } catch {
    return null;
  }
}
