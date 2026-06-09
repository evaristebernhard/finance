#!/usr/bin/env node

import net from "node:net";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import readline from "node:readline";

function parseArgs(argv) {
  const args = {
    publicAddr: "127.0.0.1:8801",
    privateAddr: "127.0.0.1:8802",
    connectTimeoutMs: 10000,
    idleTimeoutMs: 30000,
    emitEvery: 0,
    runDir: null,
    offlineRunDir: null,
    summaryWaitMs: 2000,
    stateUrl: null,
    statePollMs: 0,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (!key.startsWith("--")) continue;
    i += 1;
    if (key === "--public-addr") args.publicAddr = value;
    else if (key === "--private-addr") args.privateAddr = value;
    else if (key === "--connect-timeout-ms") args.connectTimeoutMs = Number(value);
    else if (key === "--idle-timeout-ms") args.idleTimeoutMs = Number(value);
    else if (key === "--emit-every") args.emitEvery = Number(value);
    else if (key === "--run-dir") args.runDir = value;
    else if (key === "--offline-run-dir") args.offlineRunDir = value;
    else if (key === "--summary-wait-ms") args.summaryWaitMs = Number(value);
    else if (key === "--state-url") args.stateUrl = value;
    else if (key === "--state-poll-ms") args.statePollMs = Number(value);
    else throw new Error(`unknown arg: ${key}`);
  }
  if (args.runDir && !path.isAbsolute(args.runDir)) {
    args.runDir = path.resolve(process.env.INIT_CWD ?? process.cwd(), args.runDir);
  }
  if (args.offlineRunDir && !path.isAbsolute(args.offlineRunDir)) {
    args.offlineRunDir = path.resolve(process.env.INIT_CWD ?? process.cwd(), args.offlineRunDir);
  }
  return args;
}

function splitAddr(raw) {
  const idx = raw.lastIndexOf(":");
  if (idx < 0) throw new Error(`bad address: ${raw}`);
  return { host: raw.slice(0, idx), port: Number(raw.slice(idx + 1)) };
}

async function connectWithRetry(rawAddr, label, timeoutMs) {
  const { host, port } = splitAddr(rawAddr);
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      return await new Promise((resolve, reject) => {
        const socket = net.createConnection({ host, port });
        socket.setNoDelay(true);
        socket.once("connect", () => resolve(socket));
        socket.once("error", reject);
      });
    } catch (err) {
      lastError = err;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }
  throw new Error(`could not connect ${label} at ${rawAddr}: ${lastError?.message ?? "timeout"}`);
}

function emptyStats() {
  return {
    run_id: null,
    done: false,
    public_events: 0,
    private_events: 0,
    market_quotes: 0,
    market_trades: 0,
    market_l2_updates: 0,
    session_start_seen: false,
    session_end_seen: false,
    last_seq: null,
    last_quote_seq: null,
    last_local_ts_us: null,
    last_mid: null,
    last_spread_bps: null,
    account: null,
    order_acks: 0,
    order_rejects: 0,
    fills: 0,
    portfolio_updates: 0,
    latency_slippage: {
      count: 0,
      sum_bps: 0,
      min_bps: null,
      max_bps: null,
      avg_bps: null,
    },
    depth_sweeps: {
      count: 0,
      partial_fills: 0,
      last: null,
    },
    runner_state: null,
    order_chains: {},
  };
}

async function readRunnerState(stateUrl) {
  if (!stateUrl) return null;
  if (typeof fetch !== "function") {
    return { error: "fetch_unavailable" };
  }
  try {
    const response = await fetch(stateUrl);
    if (!response.ok) {
      return { error: `http_${response.status}` };
    }
    return await response.json();
  } catch (err) {
    return { error: err.message };
  }
}

function readJsonIfExists(path) {
  if (!fs.existsSync(path)) return null;
  try {
    return JSON.parse(fs.readFileSync(path, "utf8"));
  } catch {
    return null;
  }
}

function readCompactEvents(runDir) {
  const path = `${runDir}/events.ndjson`;
  if (!fs.existsSync(path)) return [];
  return fs
    .readFileSync(path, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

async function waitForSummary(runDir, waitMs) {
  if (!runDir) return null;
  const path = `${runDir}/summary.json`;
  const deadline = Date.now() + waitMs;
  while (Date.now() < deadline) {
    const value = readJsonIfExists(path);
    if (value) return value;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return readJsonIfExists(path);
}

function compactEventAudit(runDir) {
  if (!runDir) return null;
  const events = readCompactEvents(runDir);
  const chains = {};
  for (const event of events) {
    const payload = event.payload ?? {};
    const intent = payload.intent ?? {};
    const nested = payload.payload ?? {};
    const intentId = payload.intent_id ?? nested.intent_id ?? intent.intent_id;
    if (intentId === undefined || intentId === null) continue;
    const key = String(intentId);
    const chain = chains[key] ?? {
      intent_id: intentId,
      events: [],
      observed_seq: null,
      arrival_seq: null,
      fill_price: null,
      latency_slippage_bps: null,
    };
    chain.events.push(event.event_type);
    chain.observed_seq = chain.observed_seq ?? payload.observed_seq ?? intent.observed_seq ?? nested.observed_seq ?? null;
    chain.arrival_seq = chain.arrival_seq ?? payload.arrival_seq ?? nested.arrival_seq ?? null;
    chain.fill_price = chain.fill_price ?? payload.fill_price ?? nested.fill_price ?? null;
    chain.latency_slippage_bps = chain.latency_slippage_bps ?? payload.latency_slippage_bps ?? nested.latency_slippage_bps ?? null;
    chains[key] = chain;
  }
  return {
    event_count: events.length,
    event_types: events.map((event) => event.event_type),
    order_chains: chains,
  };
}

function payloadOf(message) {
  return message?.payload ?? {};
}

function updateLatency(stats, payload) {
  const value = payload?.latency_slippage_bps;
  if (typeof value !== "number" || !Number.isFinite(value)) return;
  const s = stats.latency_slippage;
  s.count += 1;
  s.sum_bps += value;
  s.min_bps = s.min_bps === null ? value : Math.min(s.min_bps, value);
  s.max_bps = s.max_bps === null ? value : Math.max(s.max_bps, value);
  s.avg_bps = s.sum_bps / s.count;
}

function updateDepth(stats, payload) {
  const sweep = payload?.depth_sweep;
  if (!sweep) return;
  stats.depth_sweeps.count += 1;
  if (sweep.partial_fill) stats.depth_sweeps.partial_fills += 1;
  stats.depth_sweeps.last = sweep;
}

function updateChain(stats, eventType, payload) {
  const intentId = payload?.intent_id;
  if (intentId === undefined || intentId === null) return;
  const key = String(intentId);
  const chain = stats.order_chains[key] ?? {
    intent_id: intentId,
    events: [],
    client_order_id: null,
    fill_price: null,
    status: null,
  };
  chain.events.push(eventType);
  if (payload.order?.client_order_id) chain.client_order_id = payload.order.client_order_id;
  if (payload.order?.status) chain.status = payload.order.status;
  if (typeof payload.fill_price === "number") chain.fill_price = payload.fill_price;
  stats.order_chains[key] = chain;
}

function observe(stats, channel, message) {
  stats.run_id = stats.run_id ?? message.run_id ?? null;
  stats.last_seq = message.seq ?? stats.last_seq;
  stats.last_quote_seq = message.quote_seq ?? stats.last_quote_seq;
  stats.last_local_ts_us = message.local_ts_us ?? stats.last_local_ts_us;
  if (channel === "public") stats.public_events += 1;
  if (channel === "private") stats.private_events += 1;

  const type = message.type;
  const payload = payloadOf(message);
  if (type === "session_start") stats.session_start_seen = true;
  else if (type === "session_end") {
    stats.session_end_seen = true;
    stats.done = true;
  } else if (type === "market_quote") {
    stats.market_quotes += 1;
    const quote = payload.quote ?? {};
    stats.last_mid = quote.mid ?? stats.last_mid;
    if (typeof quote.ask === "number" && typeof quote.bid === "number" && typeof quote.mid === "number" && quote.mid > 0) {
      stats.last_spread_bps = ((quote.ask - quote.bid) / quote.mid) * 10000;
    }
  } else if (type === "market_trade") {
    stats.market_trades += 1;
  } else if (type === "market_l2_update") {
    stats.market_l2_updates += 1;
  } else if (type === "account_snapshot") {
    stats.account = payload.account ?? stats.account;
    stats.portfolio_updates += 1;
  } else if (type === "order_ack") {
    stats.order_acks += 1;
    const inner = payloadOf(message);
    updateChain(stats, type, inner);
  } else if (type === "order_reject") {
    stats.order_rejects += 1;
  } else if (type === "fill") {
    stats.fills += 1;
    const inner = payloadOf(message);
    updateLatency(stats, inner);
    updateDepth(stats, inner);
    updateChain(stats, type, inner);
  }
}

function attachReader(socket, channel, stats, onMessage) {
  const rl = readline.createInterface({ input: socket });
  rl.on("line", (line) => {
    if (!line.trim()) return;
    try {
      const message = JSON.parse(line);
      observe(stats, channel, message);
      onMessage(stats, message);
    } catch (err) {
      console.error(`monitor_json_error channel=${channel}: ${err.message}`);
    }
  });
  rl.on("close", () => {
    onMessage(stats, { type: `${channel}_closed` });
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.offlineRunDir) {
    console.log(
      JSON.stringify(
        {
          type: "monitor_offline_audit",
          run_summary: await waitForSummary(args.offlineRunDir, args.summaryWaitMs),
          compact_event_audit: compactEventAudit(args.offlineRunDir),
        },
        null,
        2,
      ),
    );
    return;
  }

  const stats = emptyStats();
  let messages = 0;
  let lastMessageAt = Date.now();

  const publicSocket = await connectWithRetry(args.publicAddr, "public", args.connectTimeoutMs);
  const privateSocket = await connectWithRetry(args.privateAddr, "private", args.connectTimeoutMs);
  let summaryPrinted = false;
  stats.runner_state = await readRunnerState(args.stateUrl);

  const stateTimer =
    args.stateUrl && args.statePollMs > 0
      ? setInterval(async () => {
          stats.runner_state = await readRunnerState(args.stateUrl);
        }, args.statePollMs)
      : null;

  function onMessage(currentStats) {
    messages += 1;
    lastMessageAt = Date.now();
    if (args.emitEvery > 0 && messages % args.emitEvery === 0) {
      console.log(JSON.stringify({ type: "monitor_snapshot", stats: currentStats }, null, 2));
    }
    if (currentStats.done && !summaryPrinted) {
      summaryPrinted = true;
      Promise.resolve()
        .then(async () => {
          const runnerState = await readRunnerState(args.stateUrl);
          return {
            type: "monitor_summary",
            stats: currentStats,
            run_summary: await waitForSummary(args.runDir, args.summaryWaitMs),
            runner_state:
              runnerState?.error && currentStats.runner_state ? currentStats.runner_state : runnerState,
            compact_event_audit: compactEventAudit(args.runDir),
          };
        })
        .then((summary) => {
          console.log(JSON.stringify(summary, null, 2));
        })
        .catch((err) => {
          console.error(`monitor_summary_error: ${err.message}`);
          console.log(JSON.stringify({ type: "monitor_summary", stats: currentStats }, null, 2));
        });
      publicSocket.destroy();
      privateSocket.destroy();
      if (stateTimer) clearInterval(stateTimer);
      process.exitCode = 0;
      setTimeout(() => process.exit(0), args.runDir ? args.summaryWaitMs + 100 : 50);
    }
  }

  attachReader(publicSocket, "public", stats, onMessage);
  attachReader(privateSocket, "private", stats, onMessage);

  const timer = setInterval(() => {
    if (Date.now() - lastMessageAt > args.idleTimeoutMs) {
      console.log(JSON.stringify({ type: "monitor_idle_timeout", stats }, null, 2));
      publicSocket.destroy();
      privateSocket.destroy();
      if (stateTimer) clearInterval(stateTimer);
      clearInterval(timer);
      process.exitCode = 2;
    }
  }, 250);
}

main().catch((err) => {
  console.error(err.stack ?? err.message);
  process.exitCode = 1;
});
