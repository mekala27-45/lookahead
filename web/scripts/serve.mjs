// Serves the static export the way GitHub Pages does, and refuses what the host refuses.
//
// Two refusals on purpose, found on Day 12's live URL after the tests had passed: HEAD requests
// get a 405 (Pages answers them with an error), so the data layer has to size a mart from the
// bundle and never from HEAD; and the mock API under /mock-api answers its first request with a
// 503, the way the Fly machine answers while it wakes, so the site's client has to probe twice.
// After the first 503 the mock answers every /v1 route from the recorded session in out/data.
// Byte range requests are honored because the parquet reader reads the footer first.
import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "out");
const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "/lookahead";
const port = Number(process.env.LOOKAHEAD_E2E_PORT ?? 4173);

if (!existsSync(join(root, "index.html"))) {
  console.error("out/index.html is missing: run `npm run build:e2e` first");
  process.exit(1);
}

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".wasm": "application/wasm",
  ".parquet": "application/vnd.apache.parquet",
};

let session = null;
function recorded() {
  if (!session) {
    const path = join(root, "data", "recorded_session.json");
    session = existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : { responses: {} };
  }
  return session;
}

// The mock API: the first request of the server's life is a 503 (the machine is waking); then
// each route is answered from the recorded session by method and path, POST /v1/forecasts by
// the authority in the body.
let firstApiRequest = true;
function mockApi(req, res, path) {
  const answer = (status, body) => {
    res.writeHead(status, { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" });
    res.end(JSON.stringify(body));
  };
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Authorization, Content-Type",
    });
    return res.end();
  }
  if (firstApiRequest) {
    firstApiRequest = false;
    return answer(503, { error: "the machine is starting", statement: "", served_at: new Date().toISOString() });
  }
  const responses = recorded().responses;
  let chunks = "";
  req.on("data", (c) => {
    chunks += c;
  });
  req.on("end", () => {
    let name = null;
    if (req.method === "POST" && path === "/v1/forecasts") {
      const authority = (() => {
        try {
          return JSON.parse(chunks || "{}").authority;
        } catch {
          return null;
        }
      })();
      if (!req.headers.authorization) return answer(401, { error: "writes need the token", statement: "", served_at: "" });
      name = authority ? `issue_${authority}` : null;
    } else if (req.method === "POST" && path === "/v1/score") name = "score";
    else if (req.method === "GET") {
      const hit = Object.entries(responses).find(([, r]) => r.method === "GET" && r.path === path);
      name = hit ? hit[0] : null;
    }
    const found = name ? responses[name] : null;
    if (!found) return answer(404, { error: `no recorded response for ${req.method} ${path}`, statement: "", served_at: "" });
    return answer(found.status, found.body);
  });
}

function send404(res) {
  const page = join(root, "404.html");
  res.writeHead(404, { "Content-Type": TYPES[".html"] });
  if (!existsSync(page)) return res.end();
  createReadStream(page).pipe(res);
}

createServer((req, res) => {
  // The host refuses HEAD; so does this server, so a client that sends one fails the tests here.
  if (req.method === "HEAD") {
    res.writeHead(405, { Allow: "GET" });
    return res.end();
  }
  const url = new URL(req.url ?? "/", "http://localhost");
  let path = decodeURIComponent(url.pathname);
  if (path.startsWith("/mock-api/")) return mockApi(req, res, path.slice("/mock-api".length));
  if (req.method !== "GET") {
    res.writeHead(405, { Allow: "GET" });
    return res.end();
  }
  if (base) {
    if (path === "/" || path === base) {
      res.writeHead(301, { Location: `${base}/` });
      return res.end();
    }
    if (!path.startsWith(`${base}/`)) return send404(res);
    path = path.slice(base.length);
  }
  let file = normalize(join(root, path));
  if (file !== root && !file.startsWith(root + sep)) return send404(res);
  if (existsSync(file) && statSync(file).isDirectory()) {
    if (!url.pathname.endsWith("/")) {
      res.writeHead(301, { Location: `${url.pathname}/${url.search}` });
      return res.end();
    }
    file = join(file, "index.html");
  }
  if (!existsSync(file) && existsSync(`${file}.html`)) file = `${file}.html`;
  if (!existsSync(file) || !statSync(file).isFile()) return send404(res);

  const size = statSync(file).size;
  const headers = {
    "Content-Type": TYPES[extname(file)] ?? "application/octet-stream",
    "Accept-Ranges": "bytes",
    "Cache-Control": "no-cache",
  };
  const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range ?? "");
  if (range && (range[1] || range[2])) {
    let start = range[1] ? Number(range[1]) : Math.max(size - Number(range[2]), 0);
    let end = range[1] && range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
    if (start >= size || start > end) {
      res.writeHead(416, { ...headers, "Content-Range": `bytes */${size}` });
      return res.end();
    }
    start = Math.max(start, 0);
    end = Math.max(end, start);
    res.writeHead(206, { ...headers, "Content-Range": `bytes ${start}-${end}/${size}`, "Content-Length": end - start + 1 });
    return createReadStream(file, { start, end }).pipe(res);
  }
  res.writeHead(200, { ...headers, "Content-Length": size });
  createReadStream(file).pipe(res);
}).listen(port, "127.0.0.1", () => {
  console.log(`serving out/ at http://127.0.0.1:${port}${base}/ (HEAD refused, first /mock-api request answers 503)`);
});
