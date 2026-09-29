// Number formats, mirroring packages/core/src/lookahead_core/formats.py so that a value reads the
// same on the site as in the memo and the README. Anything that rounds to zero prints unsigned.
export type Scalar = number | string | boolean | null;

export const FORMATS = [
  "int",
  "float1",
  "float2",
  "float3",
  "float4",
  "pct0",
  "pct1",
  "pct2",
  "pct3",
  "spct1",
  "spct2",
  "float0",
  "float6",
  "usd0",
  "usd2",
  "usdm",
  "usdb",
  "bps",
  "mw",
  "hours1",
  "shours1",
  "kwh3",
  "ms",
  "text",
] as const;
export type Fmt = (typeof FORMATS)[number];

/**
 * Fixed decimals with thousands separators, rounded the way Python's format() rounds: on the
 * exact binary value of the number, ties to even. toFixed(100) is the exact expansion for every
 * magnitude this site prints, so the decision is made on real digits rather than on the shortest
 * decimal that happens to print for the number.
 */
function grouped(n: number, decimals: number): string {
  const negative = n < 0 || Object.is(n, -0);
  const [whole = "0", frac = ""] = Math.abs(n).toFixed(100).split(".");
  const digits = (whole + frac.slice(0, decimals)).split("").map(Number);
  const rest = frac.slice(decimals);
  const first = Number(rest[0] ?? "0");
  const tied = first === 5 && !/[1-9]/.test(rest.slice(1));
  const last = digits[digits.length - 1] ?? 0;
  if (first > 5 || (first === 5 && !tied) || (tied && last % 2 === 1)) {
    let i = digits.length - 1;
    while (i >= 0) {
      const d = (digits[i] ?? 0) + 1;
      digits[i] = d % 10;
      if (d < 10) break;
      i -= 1;
    }
    if (i < 0) digits.unshift(1);
  }
  const intDigits = digits.slice(0, digits.length - decimals).join("") || "0";
  const intText = intDigits.replace(/^0+(?=\d)/, "").replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const fracText = decimals > 0 ? `.${digits.slice(digits.length - decimals).join("")}` : "";
  return `${negative ? "-" : ""}${intText}${fracText}`;
}

const isZero = (text: string): boolean => Number(text.replace(/[,-]/g, "")) === 0;

const plain = (n: number, decimals: number): string => {
  const text = grouped(n, decimals);
  return text.startsWith("-") && isZero(text) ? text.slice(1) : text;
};

const money = (n: number, body: string, suffix = ""): string => `${n < 0 && !isZero(body) ? "-" : ""}$${body}${suffix}`;

/** One formatter for every figure on the site. The format names are the manifest's `fmt`. */
export function formatValue(value: Scalar | undefined, fmt: string): string {
  if (fmt === "text") return value === null || value === undefined ? "not available" : String(value);
  if (value === null || value === undefined) return "not applicable";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "not available";
  switch (fmt) {
    case "int":
      return plain(n, 0);
    case "float1":
      return plain(n, 1);
    case "float2":
      return plain(n, 2);
    case "float3":
      return plain(n, 3);
    case "float4":
      return plain(n, 4);
    case "pct0":
      return `${plain(n * 100, 0)}%`;
    case "pct1":
      return `${plain(n * 100, 1)}%`;
    case "pct2":
      return `${plain(n * 100, 2)}%`;
    case "pct3":
      return `${plain(n * 100, 3)}%`;
    case "spct1": {
      const text = plain(n * 100, 1);
      return `${n > 0 && !isZero(text) ? "+" : ""}${text}%`;
    }
    case "spct2": {
      const text = plain(n * 100, 2);
      return `${n > 0 && !isZero(text) ? "+" : ""}${text}%`;
    }
    case "float0":
      return plain(n, 0);
    case "float6":
      return plain(n, 6);
    case "mw":
      return `${plain(n, 0)} MW`;
    case "hours1":
      return `${plain(n, 1)} h`;
    case "shours1": {
      const text = plain(n, 1);
      return `${n > 0 && !isZero(text) ? "+" : ""}${text} h`;
    }
    case "kwh3":
      return `${plain(n, 3)} kWh`;
    case "ms":
      return `${plain(n, 0)} ms`;
    case "usd0":
      return money(n, grouped(Math.abs(n), 0));
    case "usd2":
      return money(n, grouped(Math.abs(n), 2));
    case "usdm":
      return money(n, grouped(Math.abs(n) / 1e6, 1), "M");
    case "usdb":
      return money(n, grouped(Math.abs(n) / 1e9, 2), "B");
    case "bps":
      return `${plain(n, 0)} bp`;
    default:
      throw new Error(`unknown format ${fmt}`);
  }
}

/** Shorthand for chart code, which formats query results rather than manifest entries. */
export const fmt = (value: Scalar | undefined, format: Fmt): string => formatValue(value, format);
