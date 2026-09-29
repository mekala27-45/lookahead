// The page carries data-ready once its first query has answered (or at once, on a page that runs
// none), so tests and anything else reading the DOM can tell a loaded chart from a skeleton.
export function markReady(): void {
  document.documentElement.setAttribute("data-ready", "true");
}
