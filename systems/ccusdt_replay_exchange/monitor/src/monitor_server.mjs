#!/usr/bin/env node

import fs from "node:fs";
import fsp from "node:fs/promises";
import http from "node:http";
import net from "node:net";
import path from "node:path";
import process from "node:process";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const srcDir = path.dirname(__filename);
const monitorDir = path.resolve(srcDir, "..");
const systemDir = path.resolve(monitorDir, "..");
const repoRoot = path.resolve(systemDir, "..", "..");
const defaultRunsRoot = path.resolve(systemDir, "runs");

function parseArgs(argv) {
  const args = {
    dev: false,
    host: "127.0.0.1",
    port: 8810,
    runsRoot: defaultRunsRoot,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--dev") args.dev = true;
    else if (key === "--host") {
      args.host = value;
      i += 1;
    } else if (key === "--port") {
      args.port = Number(value);
      i += 1;
    } else if (key === "--runs-root") {
      args.runsRoot = path.resolve(value);
      i += 1;
    } else {
      throw new Error(`unknown arg: ${key}`);
    }
  }
  return args;
}

function lowerNorm(value) {
  return path.resolve(value).toLowerCase();
}

function ensureInside(child, parent) {
  const normalizedChild = lowerNorm(child);
  const normalizedParent = lowerNorm(parent);
  return normalizedChild === normalizedParent || normalizedChild.startsWith(`${normalizedParent}${path.sep}`);
}

function resolveRunDir(rawRunDir, runsRoot) {
  if (!rawRunDir) throw httpError(400, "missing runDir");
  let candidate;
  if (path.isAbsolute(rawRunDir)) {
    candidate = path.resolve(rawRunDir);
  } else if (rawRunDir.replaceAll("\\", "/").startsWith("systems/ccusdt_replay_exchange/runs/")) {
    candidate = path.resolve(repoRoot, rawRunDir);
  } else {
    candidate = path.resolve(runsRoot, rawRunDir);
  }
  if (!ensureInside(candidate, runsRoot)) {
    throw httpError(403, "runDir must stay inside systems/ccusdt_replay_exchange/runs");
  }
  return candidate;
}

function httpError(status, message) {
  const err = new Error(message);
  err.status = status;
  return err;
}

function sendJson(res, value, status = 200) {
  const text = JSON.stringify(value, null, 2);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  res.end(text);
}

function sendError(res, err) {
  sendJson(res, { error: err.message ?? String(err) }, err.status ?? 500);
}

async function readJsonIfExists(filePath) {
  try {
    const raw = await fsp.readFile(filePath, "utf8");
    return JSON.parse(raw);
  } catch (err) {
    if (err.code === "ENOENT") return null;
    return { _parse_error: err.message };
  }
}

async function exists(filePath) {
  try {
    await fsp.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function listRuns(runsRoot) {
  const rows = [];
  async function walk(dir, depth) {
    if (depth > 3) return;
    let entries = [];
    try {
      entries = await fsp.readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }
    const hasSummary = entries.some((entry) => entry.isFile() && entry.name === "summary.json");
    const hasEvents = entries.some((entry) => entry.isFile() && entry.name === "events.ndjson");
    if (hasSummary || hasEvents) {
      const stat = await fsp.stat(dir);
      const rel = path.relative(runsRoot, dir).replaceAll("\\", "/");
      const summary = await readJsonIfExists(path.join(dir, "summary.json"));
      rows.push({
        run_id: summary?.run_id ?? path.basename(dir),
        run_dir: rel,
        has_summary: hasSummary,
        has_events: hasEvents,
        mtime_ms: stat.mtimeMs,
        source_label: summary?.source_label ?? null,
        transport_profile: summary?.public_stream_mode ?? summary?.transport_profile ?? null,
        fill_model: summary?.fill_model ?? null,
        orders_submitted: summary?.orders_submitted ?? null,
        fills_created: summary?.fills_created ?? null,
      });
    }
    for (const entry of entries) {
      if (entry.isDirectory()) {
        await walk(path.join(dir, entry.name), depth + 1);
      }
    }
  }
  await walk(runsRoot, 0);
  rows.sort((a, b) => b.mtime_ms - a.mtime_ms);
  return rows;
}

function pickIntentId(event) {
  const p = event.payload ?? {};
  const inner = p.payload ?? {};
  const intent = p.intent ?? inner.intent ?? {};
  return p.intent_id ?? inner.intent_id ?? intent.intent_id ?? p.order?.intent_id ?? inner.order?.intent_id ?? null;
}

function eventLocalTs(event) {
  const p = event.payload ?? {};
  const inner = p.payload ?? {};
  return p.local_ts_us ?? inner.local_ts_us ?? p.observed_local_ts_us ?? inner.observed_local_ts_us ?? null;
}

function eventObservedSeq(event) {
  const p = event.payload ?? {};
  const inner = p.payload ?? {};
  const intent = p.intent ?? inner.intent ?? {};
  return p.observed_seq ?? inner.observed_seq ?? intent.observed_seq ?? null;
}

function compactQuote(quote) {
  if (!quote) return null;
  return {
    bid: quote.bid ?? null,
    ask: quote.ask ?? null,
    mid: quote.mid ?? null,
    seq: quote.seq ?? null,
    local_ts_us: quote.local_ts_us ?? null,
    exchange_ts_us: quote.exchange_ts_us ?? null,
  };
}

function ensureChain(chains, intentId) {
  const key = String(intentId);
  if (!chains.has(key)) {
    chains.set(key, {
      intent_id: intentId,
      event_ids: [],
      events: [],
      first_event_id: null,
      last_event_id: null,
      status: "pending",
      side: null,
      client_order_id: null,
      cell: null,
      capacity_source: null,
      requested_exposure: null,
      actual_exposure: null,
      clipped_exposure: null,
      skipped: false,
      shadow_position_id: null,
      observed_seq: null,
      arrival_seq: null,
      observed_local_ts_us: null,
      arrival_local_ts_us: null,
      observed_quote: null,
      arrival_quote: null,
      fill_price: null,
      fill_qty: null,
      spread_bps_at_arrival: null,
      latency_slippage_bps: null,
      bridge_wall_latency_ms: null,
      lot: null,
      account: null,
      raw: {},
    });
  }
  return chains.get(key);
}

function mergeSignal(chain, signal) {
  if (!signal) return;
  chain.raw.shadow_signal = chain.raw.shadow_signal ?? signal;
  chain.side = chain.side ?? signal.side ?? signal.direction_label ?? null;
  chain.cell = chain.cell ?? signal.cell ?? null;
  chain.shadow_position_id = chain.shadow_position_id ?? signal.shadow_position_id ?? null;
  chain.observed_seq = chain.observed_seq ?? signal.observed_seq ?? null;
  chain.observed_local_ts_us = chain.observed_local_ts_us ?? signal.local_ts_us ?? signal.entry_ts_us ?? null;
  chain.requested_exposure = chain.requested_exposure ?? signal.requested_exposure ?? null;
  chain.actual_exposure = chain.actual_exposure ?? signal.actual_exposure ?? null;
  chain.clipped_exposure = chain.clipped_exposure ?? signal.clipped_exposure ?? null;
  chain.capacity_source = chain.capacity_source ?? signal.capacity_source ?? null;
  if (typeof signal.skipped === "boolean") chain.skipped = signal.skipped;
  const closed = Array.isArray(signal.closed_now) ? signal.closed_now[0] : null;
  if (closed) {
    chain.lot = chain.lot ?? closed.position_lot ?? null;
    chain.shadow_position_id = chain.shadow_position_id ?? closed.shadow_position_id ?? null;
    chain.cell = chain.cell ?? closed.cell ?? null;
  }
}

function mergeCapacity(chain, capacity) {
  if (!capacity) return;
  chain.raw.capacity_decision = chain.raw.capacity_decision ?? capacity;
  chain.capacity_source = chain.capacity_source ?? capacity.capacity_source ?? null;
  chain.requested_exposure = chain.requested_exposure ?? capacity.requested_exposure ?? null;
  chain.actual_exposure = chain.actual_exposure ?? capacity.actual_exposure ?? null;
  chain.clipped_exposure = chain.clipped_exposure ?? capacity.clipped_exposure ?? null;
  chain.shadow_position_id = chain.shadow_position_id ?? capacity.shadow_position_id ?? null;
  if (typeof capacity.skipped === "boolean") chain.skipped = capacity.skipped;
}

function updateChainFromEvent(chains, event) {
  const intentId = pickIntentId(event);
  if (intentId === null || intentId === undefined) return;
  const chain = ensureChain(chains, intentId);
  const p = event.payload ?? {};
  const inner = p.payload ?? {};
  const signal = p.shadow_signal ?? inner.shadow_signal ?? p.intent?.shadow_signal ?? null;
  const capacity = p.capacity_decision ?? signal?.capacity_decision ?? null;

  chain.event_ids.push(event.event_id ?? null);
  chain.events.push(event.event_type);
  chain.first_event_id = chain.first_event_id ?? event.event_id ?? null;
  chain.last_event_id = event.event_id ?? chain.last_event_id;
  chain.observed_seq = chain.observed_seq ?? eventObservedSeq(event);
  chain.observed_local_ts_us = chain.observed_local_ts_us ?? eventLocalTs(event);

  mergeSignal(chain, signal);
  mergeCapacity(chain, capacity);

  if (event.event_type === "order_scheduled") {
    chain.raw.order_scheduled = p;
    chain.arrival_local_ts_us = chain.arrival_local_ts_us ?? p.arrival_local_ts_us ?? null;
    chain.bridge_wall_latency_ms = chain.bridge_wall_latency_ms ?? p.bridge_wall_latency_ms ?? null;
    chain.status = chain.status === "pending" ? "scheduled" : chain.status;
  } else if (event.event_type === "order_arrived") {
    chain.raw.order_arrived = p;
    chain.arrival_seq = chain.arrival_seq ?? p.arrival_seq ?? null;
    chain.arrival_local_ts_us = chain.arrival_local_ts_us ?? p.arrival_local_ts_us ?? null;
    chain.observed_quote = chain.observed_quote ?? compactQuote(p.observed_quote);
    chain.arrival_quote = chain.arrival_quote ?? compactQuote(p.arrival_quote);
    chain.spread_bps_at_arrival = chain.spread_bps_at_arrival ?? p.spread_bps_at_arrival ?? null;
    chain.latency_slippage_bps = chain.latency_slippage_bps ?? p.latency_slippage_bps ?? null;
    chain.bridge_wall_latency_ms = chain.bridge_wall_latency_ms ?? p.bridge_wall_latency_ms ?? null;
    if (p.order) {
      chain.side = chain.side ?? p.order.side ?? null;
      chain.client_order_id = chain.client_order_id ?? p.order.client_order_id ?? null;
    }
    chain.status = chain.status === "pending" || chain.status === "scheduled" ? "arrived" : chain.status;
  } else if (event.event_type === "order_ack") {
    chain.raw.order_ack = inner;
    chain.status = inner.order?.status ?? "ack";
    chain.side = chain.side ?? inner.order?.side ?? null;
    chain.client_order_id = chain.client_order_id ?? inner.order?.client_order_id ?? null;
    chain.fill_price = chain.fill_price ?? inner.fill_price ?? inner.order?.avg_fill_price ?? null;
    chain.fill_qty = chain.fill_qty ?? inner.order?.filled_qty ?? null;
    chain.observed_quote = chain.observed_quote ?? compactQuote(inner.observed_quote);
    chain.arrival_quote = chain.arrival_quote ?? compactQuote(inner.arrival_quote);
    chain.spread_bps_at_arrival = chain.spread_bps_at_arrival ?? inner.spread_bps_at_arrival ?? null;
    chain.latency_slippage_bps = chain.latency_slippage_bps ?? inner.latency_slippage_bps ?? null;
  } else if (event.event_type === "order_reject") {
    chain.raw.order_reject = inner;
    chain.status = "rejected";
  } else if (event.event_type === "fill") {
    chain.raw.fill = inner;
    chain.status = "filled";
    chain.fill_price = chain.fill_price ?? inner.fill_price ?? inner.fill?.price ?? null;
    chain.fill_qty = chain.fill_qty ?? inner.fill?.qty ?? null;
    chain.side = chain.side ?? inner.fill?.side ?? null;
    chain.observed_quote = chain.observed_quote ?? compactQuote(inner.observed_quote);
    chain.arrival_quote = chain.arrival_quote ?? compactQuote(inner.arrival_quote);
    chain.spread_bps_at_arrival = chain.spread_bps_at_arrival ?? inner.spread_bps_at_arrival ?? null;
    chain.latency_slippage_bps = chain.latency_slippage_bps ?? inner.latency_slippage_bps ?? null;
  } else if (event.event_type === "portfolio_state_on_change" || event.event_type === "portfolio_state") {
    chain.raw.portfolio = p;
    chain.account = p.account ?? inner.account ?? p.portfolio ?? inner.portfolio ?? null;
  } else if (event.event_type === "capacity_decision") {
    chain.status = chain.skipped ? "skipped" : chain.status;
  }
}

async function parseEvents(eventsPath) {
  const eventTypeCounts = {};
  const chains = new Map();
  let eventCount = 0;
  let badJson = 0;

  if (!(await exists(eventsPath))) {
    return { event_count: 0, bad_json: 0, chains: [], eventTypeCounts, has_events: false };
  }

  const stream = fs.createReadStream(eventsPath, { encoding: "utf8" });
  const rl = readline.createInterface({ input: stream, crlfDelay: Infinity });
  for await (const line of rl) {
    if (!line.trim()) continue;
    try {
      const event = JSON.parse(line);
      eventCount += 1;
      eventTypeCounts[event.event_type] = (eventTypeCounts[event.event_type] ?? 0) + 1;
      updateChainFromEvent(chains, event);
    } catch {
      badJson += 1;
    }
  }

  const chainRows = [...chains.values()].sort((a, b) => {
    const left = Number(a.observed_local_ts_us ?? a.first_event_id ?? 0);
    const right = Number(b.observed_local_ts_us ?? b.first_event_id ?? 0);
    return left - right;
  });

  return {
    event_count: eventCount,
    bad_json: badJson,
    chains: chainRows,
    eventTypeCounts,
    has_events: true,
  };
}

function normalizeSummary(summary, profileManifest, parsedEvents) {
  const transportProfile =
    summary?.public_stream_mode ??
    profileManifest?.transport_profile?.name ??
    summary?.transport_profile ??
    null;
  const fillProfile = summary?.fill_model ?? profileManifest?.fill_profile?.name ?? null;
  return {
    run_id: summary?.run_id ?? null,
    run_dir: summary?.run_dir ?? null,
    source_label: summary?.source_label ?? null,
    determinism_mode: summary?.determinism_mode ?? null,
    transport_profile: transportProfile,
    fill_profile: fillProfile,
    latency_profile: profileManifest?.latency_profile?.name ?? summary?.determinism_mode ?? null,
    policy_profile: profileManifest?.policy_profile?.name ?? null,
    capacity_profile: profileManifest?.capacity_profile?.name ?? null,
    exit_profile: profileManifest?.exit_profile?.name ?? null,
    orders_submitted: summary?.orders_submitted ?? null,
    fills_created: summary?.fills_created ?? null,
    intents_created: summary?.intents_created ?? null,
    event_count: summary?.event_count ?? parsedEvents.event_count,
    arrival_quote_lag_count: summary?.arrival_quote_lag_count ?? null,
    bridge_errors: summary?.bridge_errors ?? null,
    final_account: summary?.final_account ?? null,
    timing_ms: summary?.timing_ms ?? null,
  };
}

function warningsFor(summary, profileManifest, parsedEvents) {
  const warnings = [];
  if (!summary) warnings.push({ level: "warn", message: "summary.json missing" });
  if (!profileManifest) warnings.push({ level: "warn", message: "profile_manifest.json missing" });
  if (!parsedEvents.has_events) warnings.push({ level: "warn", message: "events.ndjson missing" });
  if (parsedEvents.bad_json > 0) warnings.push({ level: "error", message: `${parsedEvents.bad_json} bad JSON lines in events.ndjson` });
  if ((summary?.bridge_errors ?? 0) > 0) warnings.push({ level: "error", message: `bridge_errors=${summary.bridge_errors}` });
  if ((summary?.arrival_quote_lag_count ?? 0) > 0) warnings.push({ level: "warn", message: `arrival_quote_lag_count=${summary.arrival_quote_lag_count}` });
  if (summary?.fills_created !== undefined) {
    const filledChains = parsedEvents.chains.filter((chain) => chain.status === "filled").length;
    if (Number(summary.fills_created) !== filledChains) {
      warnings.push({ level: "warn", message: `summary fills_created=${summary.fills_created}, parsed filled chains=${filledChains}` });
    }
  }
  const positionQty = summary?.final_account?.position_qty;
  if (typeof positionQty === "number" && Math.abs(positionQty) > 1e-9) {
    warnings.push({ level: "warn", message: `final residual position_qty=${positionQty}` });
  }
  return warnings;
}

async function loadOfflineRun(runDir) {
  const summary = await readJsonIfExists(path.join(runDir, "summary.json"));
  const manifest = await readJsonIfExists(path.join(runDir, "manifest.json"));
  const profileManifest = await readJsonIfExists(path.join(runDir, "profile_manifest.json"));
  const parsedEvents = await parseEvents(path.join(runDir, "events.ndjson"));
  const relRunDir = path.relative(defaultRunsRoot, runDir).replaceAll("\\", "/");
  return {
    mode: "offline",
    loaded_at: new Date().toISOString(),
    run_dir: relRunDir.startsWith("..") ? runDir : relRunDir,
    summary: normalizeSummary(summary, profileManifest, parsedEvents),
    manifest,
    profile_manifest: profileManifest,
    chains: parsedEvents.chains,
    eventTypeCounts: parsedEvents.eventTypeCounts,
    warnings: warningsFor(summary, profileManifest, parsedEvents),
  };
}

function splitAddr(rawAddr) {
  const idx = rawAddr.lastIndexOf(":");
  if (idx < 0) throw new Error(`bad address: ${rawAddr}`);
  return { host: rawAddr.slice(0, idx), port: Number(rawAddr.slice(idx + 1)) };
}

function connectSocket(rawAddr) {
  const { host, port } = splitAddr(rawAddr);
  return net.createConnection({ host, port });
}

function emptyLiveStats() {
  return {
    run_id: null,
    connected: true,
    public_events: 0,
    private_events: 0,
    market_quotes: 0,
    market_trades: 0,
    market_l2_updates: 0,
    order_acks: 0,
    order_rejects: 0,
    fills: 0,
    portfolio_updates: 0,
    last_seq: null,
    last_quote_seq: null,
    last_local_ts_us: null,
    last_mid: null,
    last_spread_bps: null,
    account: null,
    runner_state: null,
    done: false,
    errors: [],
  };
}

function observeLive(stats, channel, message) {
  stats.run_id = stats.run_id ?? message.run_id ?? null;
  stats.last_seq = message.seq ?? stats.last_seq;
  stats.last_quote_seq = message.quote_seq ?? stats.last_quote_seq;
  stats.last_local_ts_us = message.local_ts_us ?? stats.last_local_ts_us;
  if (channel === "public") stats.public_events += 1;
  if (channel === "private") stats.private_events += 1;
  const payload = message.payload ?? {};
  if (message.type === "market_quote") {
    stats.market_quotes += 1;
    const quote = payload.quote ?? {};
    stats.last_mid = quote.mid ?? stats.last_mid;
    if (typeof quote.ask === "number" && typeof quote.bid === "number" && typeof quote.mid === "number" && quote.mid > 0) {
      stats.last_spread_bps = ((quote.ask - quote.bid) / quote.mid) * 10000;
    }
  } else if (message.type === "market_trade") stats.market_trades += 1;
  else if (message.type === "market_l2_update") stats.market_l2_updates += 1;
  else if (message.type === "account_snapshot") {
    stats.account = payload.account ?? stats.account;
    stats.portfolio_updates += 1;
  } else if (message.type === "order_ack") stats.order_acks += 1;
  else if (message.type === "order_reject") stats.order_rejects += 1;
  else if (message.type === "fill") stats.fills += 1;
  else if (message.type === "session_end") stats.done = true;
}

async function fetchRunnerState(stateUrl) {
  if (!stateUrl || typeof fetch !== "function") return null;
  try {
    const response = await fetch(stateUrl);
    if (!response.ok) return { error: `http_${response.status}` };
    return await response.json();
  } catch (err) {
    return { error: err.message };
  }
}

function handleLiveStream(req, res, url) {
  const publicAddr = url.searchParams.get("publicAddr") || "127.0.0.1:8801";
  const privateAddr = url.searchParams.get("privateAddr") || "127.0.0.1:8802";
  const stateUrl = url.searchParams.get("stateUrl") || "";
  const stats = emptyLiveStats();
  const sockets = [];
  let closed = false;
  let lastEmit = 0;

  res.writeHead(200, {
    "content-type": "text/event-stream; charset=utf-8",
    "cache-control": "no-store",
    connection: "keep-alive",
  });

  function send(type, data) {
    if (closed) return;
    res.write(`event: ${type}\n`);
    res.write(`data: ${JSON.stringify(data)}\n\n`);
  }

  function maybeSnapshot(force = false) {
    const now = Date.now();
    if (!force && now - lastEmit < 500) return;
    lastEmit = now;
    send("snapshot", { mode: "live", stats });
  }

  function attach(rawAddr, channel) {
    const socket = connectSocket(rawAddr);
    sockets.push(socket);
    socket.setNoDelay(true);
    socket.on("error", (err) => {
      stats.errors.push(`${channel}: ${err.message}`);
      maybeSnapshot(true);
    });
    socket.on("close", () => {
      stats.errors.push(`${channel}: closed`);
      maybeSnapshot(true);
    });
    const rl = readline.createInterface({ input: socket });
    rl.on("line", (line) => {
      if (!line.trim()) return;
      try {
        observeLive(stats, channel, JSON.parse(line));
        maybeSnapshot(stats.done);
      } catch (err) {
        stats.errors.push(`${channel}: bad json ${err.message}`);
        maybeSnapshot(true);
      }
    });
  }

  try {
    attach(publicAddr, "public");
    attach(privateAddr, "private");
    send("snapshot", { mode: "live", stats });
  } catch (err) {
    send("error", { error: err.message });
  }

  const stateTimer = setInterval(async () => {
    stats.runner_state = await fetchRunnerState(stateUrl);
    maybeSnapshot(true);
  }, 1000);

  req.on("close", () => {
    closed = true;
    clearInterval(stateTimer);
    for (const socket of sockets) socket.destroy();
  });
}

async function handleApi(req, res, args) {
  const url = new URL(req.url, `http://${req.headers.host ?? "127.0.0.1"}`);
  if (url.pathname === "/api/runs") {
    sendJson(res, { runs: await listRuns(args.runsRoot) });
    return true;
  }
  if (url.pathname === "/api/offline-run") {
    const runDir = resolveRunDir(url.searchParams.get("runDir"), args.runsRoot);
    sendJson(res, await loadOfflineRun(runDir));
    return true;
  }
  if (url.pathname === "/api/live-stream") {
    handleLiveStream(req, res, url);
    return true;
  }
  return false;
}

function serveStatic(req, res) {
  const distDir = path.join(monitorDir, "dist");
  const url = new URL(req.url, "http://local");
  const requested = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
  const target = path.resolve(distDir, requested);
  if (!ensureInside(target, distDir)) {
    res.writeHead(403);
    res.end("forbidden");
    return;
  }
  const finalTarget = fs.existsSync(target) && fs.statSync(target).isFile() ? target : path.join(distDir, "index.html");
  const ext = path.extname(finalTarget);
  const contentType =
    ext === ".html" ? "text/html; charset=utf-8" :
    ext === ".js" ? "text/javascript; charset=utf-8" :
    ext === ".css" ? "text/css; charset=utf-8" :
    "application/octet-stream";
  fs.createReadStream(finalTarget)
    .on("error", () => {
      res.writeHead(404);
      res.end("not found");
    })
    .once("open", () => {
      res.writeHead(200, { "content-type": contentType });
    })
    .pipe(res);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  args.runsRoot = path.resolve(args.runsRoot);
  if (!ensureInside(args.runsRoot, defaultRunsRoot)) {
    throw new Error("--runs-root must stay inside systems/ccusdt_replay_exchange/runs");
  }

  let vite = null;
  if (args.dev) {
    const { createServer } = await import("vite");
    vite = await createServer({
      root: monitorDir,
      appType: "spa",
      server: { middlewareMode: true },
    });
  }

  const server = http.createServer(async (req, res) => {
    try {
      if (await handleApi(req, res, args)) return;
      if (vite) {
        vite.middlewares(req, res, (err) => {
          if (err) vite.ssrFixStacktrace(err);
          if (err) sendError(res, err);
        });
      } else {
        serveStatic(req, res);
      }
    } catch (err) {
      sendError(res, err);
    }
  });

  server.listen(args.port, args.host, () => {
    console.log(`ccusdt replay monitor listening at http://${args.host}:${args.port}`);
  });
}

main().catch((err) => {
  console.error(err.stack ?? err.message);
  process.exitCode = 1;
});
