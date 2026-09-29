// The browser build of DuckDB-WASM, imported by path so the server pass never resolves the node
// build; its types are the package's own browser types.
declare module "@duckdb/duckdb-wasm/dist/duckdb-browser.mjs" {
  export * from "@duckdb/duckdb-wasm";
}
