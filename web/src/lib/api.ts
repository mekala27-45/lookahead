// The live API and its recorded stand in. The first call on a page probes /v1/health with a six
// second limit, twice, because the API's machine stops when idle and the first request wakes it;
// if it is asleep or unreachable, every API feature on the page answers from recorded_session.json
// for the rest of the visit and says so beside the control it affects.
import { API, dataUrl } from "./site";

export type Source = "live" | "recorded";

export interface Envelope {
  statement: string;
  served_at: string;
}
export interface HealthResponse extends Envelope {
  status: string;
  environment: string;
  database: string;
  model_version: string | null;
  backend: string | null;
  authorities: number;
  writes: string;
}
export interface AuthorityOrigin {
  authority: string;
  latest_origin: string;
}
export interface AuthoritiesResponse extends Envelope {
  authorities: AuthorityOrigin[];
}
export interface ForecastRowOut {
  horizon: number;
  target_hour: string;
  q05: number;
  q25: number;
  q50: number;
  q75: number;
  q95: number;
}
export interface ScoreOut {
  horizon: number;
  target_hour: string;
  actual: number;
  abs_pct_error: number;
  inside_50: boolean;
  inside_90: boolean;
}
export interface ForecastOut extends Envelope {
  forecast_id: string;
  authority: string;
  origin: string;
  model_version: string;
  backend: string;
  spec_hash: string;
  data_source: string;
  horizons: number;
  note: string;
  issued_at: string;
  scored_at: string | null;
  scored_rows: number;
  rows?: ForecastRowOut[];
  scores?: ScoreOut[];
  scored_share?: number;
  stored_rows?: number;
}
export interface ScorecardResponse extends Envelope {
  forecasts: number;
  rows: number;
  scored_rows: number;
  unscored_share: number;
  mape: number | null;
  coverage_90: number | null;
  coverage_50: number | null;
  by_authority: { authority: string; scored_rows: number; mape: number }[];
}
export interface ScoreResponse extends Envelope {
  scored_rows: number;
  forecasts_touched: number;
  forecasts: number;
  unscored_share: number;
}
export interface ForecastListResponse extends Envelope {
  forecasts: ForecastOut[];
}

interface RecordedResponse {
  method: string;
  path: string;
  status: number;
  request?: unknown;
  body: unknown;
}
export interface RecordedSession {
  recorded: boolean;
  recorded_at: string;
  base_url: string;
  responses: Record<string, RecordedResponse>;
}

export interface Answer<T> {
  source: Source;
  status: number;
  body: T;
  /** Why the answer is the recorded one when the API itself is awake. */
  reason?: string;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const PROBE_TIMEOUT_MS = 6000;
// The API's machine stops when idle and starts on the first request, which the first probe often
// meets as a 503 or a timeout; one more try after a short pause finds it awake.
const PROBE_ATTEMPTS = 2;
const PROBE_PAUSE_MS = 4000;

let probe: Promise<Source> | null = null;
let session: Promise<RecordedSession> | null = null;

async function probeOnce(): Promise<Source> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const response = await fetch(`${API}/v1/health`, { signal: controller.signal, cache: "no-store" });
    if (!response.ok) return "recorded";
    const body = (await response.json()) as Partial<HealthResponse>;
    return body.status === "ok" ? "live" : "recorded";
  } catch {
    return "recorded";
  } finally {
    window.clearTimeout(timer);
  }
}

/** Whether this page visit talks to the live API or to the recording. Probed twice, then fixed. */
export function apiSource(): Promise<Source> {
  probe ??= (async (): Promise<Source> => {
    if (!API) return "recorded";
    for (let attempt = 1; attempt <= PROBE_ATTEMPTS; attempt += 1) {
      if (attempt > 1) await new Promise((resolve) => window.setTimeout(resolve, PROBE_PAUSE_MS));
      if ((await probeOnce()) === "live") return "live";
    }
    return "recorded";
  })();
  return probe;
}

export function recordedSession(): Promise<RecordedSession> {
  session ??= fetch(dataUrl("recorded_session.json")).then((r) => {
    if (!r.ok) throw new Error(`the recorded session did not load (${r.status})`);
    return r.json() as Promise<RecordedSession>;
  });
  return session;
}

async function fromRecording<T>(name: string, reason?: string): Promise<Answer<T>> {
  const s = await recordedSession();
  const hit = s.responses[name];
  if (!hit) throw new Error(`the recorded session has no response named ${name}`);
  return { source: "recorded", status: hit.status, body: hit.body as T, reason };
}

async function send<T>(path: string, init: RequestInit = {}): Promise<{ status: number; body: T }> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await response.json().catch(() => ({}))) as T & { error?: string };
  if (!response.ok) throw new ApiError(response.status, typeof body.error === "string" ? body.error : `status ${response.status}`);
  return { status: response.status, body };
}

/** A read: the live answer when the API is awake, else the recorded one under the given name. */
export async function read<T>(path: string, recordedName: string): Promise<Answer<T>> {
  if ((await apiSource()) === "live") {
    try {
      const { status, body } = await send<T>(path);
      return { source: "live", status, body };
    } catch {
      return fromRecording<T>(recordedName, "the live API did not answer this request");
    }
  }
  return fromRecording<T>(recordedName);
}

/**
 * Issue a forecast for an authority. Writes need the token and a live API; without either, the
 * answer is the forecast the recording issued for that authority, labelled as recorded.
 */
export async function issueForecast(authority: string, token: string): Promise<Answer<ForecastOut>> {
  const name = `issue_${authority}`;
  if ((await apiSource()) !== "live") return fromRecording<ForecastOut>(name);
  if (!token.trim()) return fromRecording<ForecastOut>(name, "no write token was given");
  const { status, body } = await send<ForecastOut>("/v1/forecasts", {
    method: "POST",
    body: JSON.stringify({ authority, note: "issued from the control room" }),
    headers: { Authorization: `Bearer ${token.trim()}` },
  });
  return { source: "live", status, body };
}

/** Read one forecast back with its rows and scores. */
export async function getForecast(forecastId: string, recordedName: string): Promise<Answer<ForecastOut>> {
  return read<ForecastOut>(`/v1/forecasts/${forecastId}`, recordedName);
}
