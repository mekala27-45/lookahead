# marginal web

The review site for Alderquist's marketing measurement: six pages (Overview, Mix, Budget, Experiments,
Targeting, Report) exported as static files and served by GitHub Pages under `/marginal`.

## Run it

```sh
npm ci
npm run dev          # http://localhost:3000/marginal/
npm run typecheck
npm run build        # writes out/, the static export
npx playwright test  # serves out/ under /marginal and runs the browser tests against it
```

The base path defaults to `/marginal`, the path Pages serves. Set `NEXT_PUBLIC_BASE_PATH=""` to build for
the root of a domain; the tests read the same variable. `npm run build` first runs
`scripts/prepare-assets.mjs`, which copies the DuckDB-WASM bundle into `public/duckdb/` and writes the
color tokens for both themes from `src/theme/palette.json`. Both outputs are ignored by git.

## The data

Everything the pages show is in `public/data/`, written by the pipeline and committed; the site never
regenerates it.

- `manifest.json`: every published figure, as values (each with a format name) and tables, each with
  its provenance. Pages print these at build time through one formatter, `src/lib/format.ts`, which
  mirrors `packages/core/src/marginal_core/formats.py`.
- `bundle.json`: the brand, the statement shown in every footer, the channels in their fixed order, and
  the measurement policy.
- `*.parquet`: the marts the charts query in the browser. DuckDB-WASM runs the SQL in a worker that
  starts after the first paint. The 1.32.0 bundle has no parquet reader of its own and would download
  one from extensions.duckdb.org, so `src/lib/data.ts` reads each file over HTTP byte ranges with
  hyparquet and hands it to DuckDB as an Arrow table named `mart_<name>`.

## The API and the recorded session

The budget and experiments pages call the live API named by `NEXT_PUBLIC_MARGINAL_API`, which the
Pages workflow sets from the `MARGINAL_API_URL` repository variable and which falls back to
`https://marginal-alderquist-api.fly.dev` when empty. The first call probes `/v1/health` with a six
second limit. If the API is asleep or unreachable, the page answers from `recorded_session.json`, a
session recorded against the real API, for the rest of the visit: the budget slider reads the surface
the pipeline solved in advance, labeled "precomputed", and "Save this plan" shows the recorded save,
labeled as recorded. A chip beside each affected control always says which source it is using.

Saving a plan to the live API needs the write token, typed into the field beside the button. It is held
in memory only and never stored.
