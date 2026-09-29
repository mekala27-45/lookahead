"use client";

import { useEffect, useState } from "react";

import { apiSource, type Source } from "@/lib/api";
import { markReady } from "@/lib/ready";

export type SourceKind = Source | "probing" | "precomputed";

const SOURCE_TEXT: Record<SourceKind, string> = {
  live: "live API",
  recorded: "recorded session (API asleep)",
  probing: "checking the live API",
  precomputed: "precomputed",
};

/** A small labeled chip that says where the numbers beside it came from. Never silent. */
export function SourceChip({ source, text, testId }: { source: SourceKind; text?: string; testId?: string }) {
  const dot =
    source === "live" ? (
      <circle cx="5" cy="5" r="4" fill="var(--lead)" />
    ) : source === "probing" ? (
      <circle cx="5" cy="5" r="3.4" fill="none" stroke="var(--control)" strokeWidth="1.4" strokeDasharray="2 1.5" />
    ) : source === "precomputed" ? (
      <rect x="1.5" y="1.5" width="7" height="7" rx="1.5" fill="var(--control)" />
    ) : (
      <circle cx="5" cy="5" r="3.4" fill="none" stroke="var(--control)" strokeWidth="1.6" />
    );
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-raised px-2 py-0.5 text-xs text-ink2 whitespace-nowrap"
      data-source={source}
      data-testid={testId}
    >
      <svg width="10" height="10" aria-hidden="true">
        {dot}
      </svg>
      {text ?? SOURCE_TEXT[source]}
    </span>
  );
}

export function sourceText(source: SourceKind): string {
  return SOURCE_TEXT[source];
}

/** Probes the live API once per page visit; "probing" until the answer or the timeout. */
export function useApiSource(): Source | "probing" {
  const [source, setSource] = useState<Source | "probing">("probing");
  useEffect(() => {
    let live = true;
    void apiSource().then((s) => {
      if (live) setSource(s);
    });
    return () => {
      live = false;
    };
  }, []);
  return source;
}

/** A row of buttons that choose one option, each a real button with aria-pressed. */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  testId,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  testId?: string;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex flex-wrap items-center gap-2" data-testid={testId}>
      <span className="text-xs text-ink2">{label}</span>
      <span className="inline-flex rounded border border-hairline overflow-hidden">
        {options.map((o) => {
          const on = o.value === value;
          return (
            <button
              key={o.value}
              type="button"
              aria-pressed={on}
              onClick={() => onChange(o.value)}
              className={`text-xs px-2.5 py-1 border-l border-hairline first:border-l-0 ${on ? "bg-ink text-surface font-semibold" : "bg-raised text-ink2 hover:text-ink"}`}
              data-value={o.value}
            >
              {o.label}
            </button>
          );
        })}
      </span>
    </div>
  );
}

/** For a page that runs no query: the page is ready once it has painted. */
export function ReadyWithoutQueries() {
  useEffect(() => {
    markReady();
  }, []);
  return null;
}
