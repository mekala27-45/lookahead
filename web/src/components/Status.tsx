import type { ReactNode } from "react";

export type StatusKind = "good" | "warning" | "serious" | "critical";

// The status colors appear only for the five conditions the build names (a failed sample ratio
// gate, a degenerate operating point, a diverged sampler, a solver that did not converge, an
// interval that excludes the truth) and always with a shape and a word, never color alone.
function Icon({ kind }: { kind: StatusKind }) {
  const color = `var(--${kind})`;
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" className="shrink-0">
      {kind === "good" ? (
        <>
          <circle cx="8" cy="8" r="7" fill={color} />
          <path
            d="M4.5 8.3l2.2 2.2 4.8-4.9"
            fill="none"
            stroke="var(--raised)"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      ) : null}
      {kind === "warning" ? (
        <>
          <path d="M8 1.2L15.2 14.3H0.8z" fill={color} />
          <path d="M8 5.8v4" stroke="var(--raised)" strokeWidth="1.8" strokeLinecap="round" />
          <circle cx="8" cy="12.1" r="1" fill="var(--raised)" />
        </>
      ) : null}
      {kind === "serious" ? (
        <>
          <path d="M5.1 1h5.8L15 5.1v5.8L10.9 15H5.1L1 10.9V5.1z" fill={color} />
          <path d="M8 4.4v4.6" stroke="var(--raised)" strokeWidth="1.8" strokeLinecap="round" />
          <circle cx="8" cy="11.6" r="1" fill="var(--raised)" />
        </>
      ) : null}
      {kind === "critical" ? (
        <>
          <circle cx="8" cy="8" r="7" fill={color} />
          <path d="M5.3 5.3l5.4 5.4M10.7 5.3l-5.4 5.4" stroke="var(--raised)" strokeWidth="1.8" strokeLinecap="round" />
        </>
      ) : null}
    </svg>
  );
}

/** A status: its icon in the status color, its word in ink so the text keeps its contrast. */
export function Status({ kind, children, testId }: { kind: StatusKind; children: ReactNode; testId?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 font-semibold text-ink" data-status={kind} data-testid={testId}>
      <Icon kind={kind} />
      <span>{children}</span>
    </span>
  );
}

/** A neutral mark for a check that passed: no status color, since passing is not a condition to flag. */
export function Passed({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-ink" data-testid={testId}>
      <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" className="shrink-0">
        <circle cx="8" cy="8" r="6.5" fill="none" stroke="var(--ink2)" strokeWidth="1.3" />
        <path d="M4.8 8.2l2 2 4.3-4.4" fill="none" stroke="var(--ink)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span>{children}</span>
    </span>
  );
}
