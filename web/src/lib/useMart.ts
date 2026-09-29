"use client";

import { useEffect, useState } from "react";

import { query, type Row } from "./data";

export interface MartState<T> {
  rows: T[] | null;
  error: string | null;
}

/**
 * Rows from a query over the marts. `initial` is what the page painted from the manifest before
 * the engine was ready, when the manifest carries the same numbers; otherwise the caller shows a
 * skeleton while rows is null.
 */
export function useMart<T extends Row>(sql: string | null, initial: T[] | null = null): MartState<T> {
  const [state, setState] = useState<MartState<T>>({ rows: initial, error: null });
  useEffect(() => {
    if (!sql) return;
    let live = true;
    query<T>(sql).then(
      (rows) => {
        if (live) setState({ rows, error: null });
      },
      (err: unknown) => {
        if (live) setState((s) => ({ rows: s.rows, error: err instanceof Error ? err.message : String(err) }));
      },
    );
    return () => {
      live = false;
    };
  }, [sql]);
  return state;
}
