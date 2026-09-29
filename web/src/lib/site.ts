// Where the site and its API live. Both are fixed at build time by next.config.ts.
export const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
export const API = process.env.NEXT_PUBLIC_LOOKAHEAD_API ?? "";

/** The URL of a file the pipeline published under public/data. */
export function dataUrl(file: string): string {
  return `${BASE}/data/${file}`;
}

export const REPO = "https://github.com/mekala27-45/lookahead";
