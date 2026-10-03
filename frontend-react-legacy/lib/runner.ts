import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import type { ManifestResponse, ReplayResponse, ReplayRow, SummaryResponse } from "./types";

type RawEvent = {
  event_type?: string;
  replay_ts?: string | number;
  payload?: Record<string, any>;
};

type LoadedRun = {
  manifest: ManifestResponse;
  rows: ReplayRow[];
  summary: SummaryResponse;
};

let cached: LoadedRun | null = null;

function runDirectory() {
  return process.env.QRS_LEGACY_RUN_DIR
    ? resolve(process.env.QRS_LEGACY_RUN_DIR)
    : resolve(process.cwd(), "..", "systems/quant_replay_engine/runs/qrs_ui_repro");
}

function asNumber(value: unknown, fallback = 0) {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function isoFromUs(value: unknown) {
  const micros = asNumber(value);
  return new Date(micros / 1000).toISOString();
}

function levelsFromBook(book: any, side: "bid" | "ask") {
  const source = Array.isArray(book?.[`${side}_depth`]) ? book[`${side}_depth`] : [];
  return source.slice(0, 25).map((level: any) => ({
    price: asNumber(level.price),
    amount: asNumber(level.qty, asNumber(level.amount, 0))
  }));
}

function loadRun(): LoadedRun {
  if (cached) return cached;
  const directory = runDirectory();
  const manifestRaw = JSON.parse(readFileSync(join(directory, "manifest.json"), "utf8"));
  const summaryRaw = JSON.parse(readFileSync(join(directory, "summary.json"), "utf8"));
  const events = readFileSync(join(directory, "events.ndjson"), "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line) as RawEvent);

  const tradesByReplayTs = new Map<string, number>();
  let currentBook: any = null;
  for (const event of events) {
    if (event.event_type === "market_trade") {
      const key = String(event.replay_ts ?? "");
      const trade = event.payload?.trade ?? {};
      const signed = trade.side === "sell" ? -1 : 1;
      tradesByReplayTs.set(key, (tradesByReplayTs.get(key) ?? 0) + signed * asNumber(trade.notional_quote));
    }
  }

  const rows: ReplayRow[] = [];
  for (const event of events) {
    if (event.event_type === "market_l2_batch" && event.payload?.book) {
      currentBook = event.payload.book;
    }
    if (event.event_type !== "market_quote") continue;
    const frame = event.payload?.frame ?? {};
    const bid = asNumber(frame.bid);
    const ask = asNumber(frame.ask);
    const mid = asNumber(frame.mid, (bid + ask) / 2);
    const bidQty = asNumber(frame.bid_qty);
    const askQty = asNumber(frame.ask_qty);
    const ts = String(frame.ts ?? event.replay_ts ?? "0");
    const imbalance = (bidQty + askQty) > 0 ? (bidQty - askQty) / (bidQty + askQty) : 0;
    const tradeFlow = tradesByReplayTs.get(String(event.replay_ts ?? "")) ?? 0;
    const bidLevels = levelsFromBook(currentBook, "bid");
    const askLevels = levelsFromBook(currentBook, "ask");
    rows.push({
      event_index: rows.length,
      timestamp: asNumber(ts),
      local_timestamp: asNumber(frame.local_ts_us, asNumber(ts)),
      timestamp_utc: isoFromUs(ts),
      best_bid_price: bid,
      best_bid_amount: bidQty,
      best_ask_price: ask,
      best_ask_amount: askQty,
      mid_price: mid,
      spread_bps: mid > 0 ? ((ask - bid) / mid) * 10_000 : 0,
      microprice: (bidQty + askQty) > 0 ? (ask * bidQty + bid * askQty) / (bidQty + askQty) : mid,
      bid_levels: bidLevels.length ? bidLevels : [{ price: bid, amount: bidQty }],
      ask_levels: askLevels.length ? askLevels : [{ price: ask, amount: askQty }],
      factors: {
        mlofi_roll10_l25: asNumber(event.payload?.signal) || imbalance,
        trade_flow_imbalance: tradeFlow === 0 ? 0 : Math.max(-1, Math.min(1, tradeFlow / 500)),
        queue_imbalance_1: imbalance,
        queue_imbalance_5: imbalance,
        ofi_l1_depth_norm: imbalance,
        microprice_dev_bps: mid > 0 ? ((asNumber(frame.microprice, mid) - mid) / mid) * 10_000 : 0,
        liquidity_shock_score: 0,
        trade_arrival_alignment: 0,
        mlofi_combo: imbalance,
        crossed_levels_removed: 0,
        trade_notional_quote: Math.abs(tradeFlow),
        panel_mid_delta_bps: 0,
        panel_mid_delta_ticks_est: 0,
        is_snapshot_batch: false,
        batch_rows: currentBook?.update_count ?? 0
      }
    });
  }

  const sourceLabel = String(manifestRaw.source_label ?? "canonical_native_stream_v1:CCUSDT:2026-10-01");
  const date = sourceLabel.match(/(\d{4}-\d{2}-\d{2})/)?.[1] ?? "2026-10-01";
  const factors = ["mlofi_roll10_l25", "trade_flow_imbalance", "queue_imbalance_1", "queue_imbalance_5", "microprice_dev_bps"];
  const manifest: ManifestResponse = {
    market: "ccusdt",
    market_label: "CCUSDT",
    run_tag: String(manifestRaw.run_id ?? "qrs_ui_repro"),
    replay_mode: "book_state_plus_factors",
    markets: [{ id: "ccusdt", label: "CCUSDT", run_tag: String(manifestRaw.run_id ?? "qrs_ui_repro"), replay_mode: "book_state_plus_factors", default_symbol: "CCUSDT", default_date: date }],
    symbols: ["CCUSDT"],
    dates: [date],
    replay_files: [{ name: "events.ndjson", status: "Runner artifact" }, { name: "replay_index.json", status: "Runner artifact" }],
    quality_daily: [],
    artifacts: ["manifest.json", "summary.json", "events.ndjson", "replay_index.json"]
  };
  const summary: SummaryResponse = {
    run_tag: manifest.run_tag,
    symbol: "CCUSDT",
    date,
    quality_hourly: [{ hour_utc: `${date}T00:00:00Z`, quality_tier: "RUNNER ARTIFACT", fill_realism_score_mean: 1 }],
    state_hourly: [{ hour_utc: `${date}T00:00:00Z`, net_potential_mean: asNumber(summaryRaw.final_account?.equity) - asNumber(manifestRaw.exchange_config?.starting_cash, 10000), spread_bps_mean: rows[0]?.spread_bps ?? 0, trade_flow_alignment_rate: 0 }],
    path_hourly: [],
    path_summary: [{ anchor_type: "runner", group_value: String(manifestRaw.profile ?? "tfi"), score: rows.length, sample_count: rows.length }],
    factor_ranking: factors.map((feature_name, index) => ({ feature_name, score: 1 - index * 0.12, side: "inspect", fold: "runner", horizon_events: 1, gate: "OBSERVED" })),
    blockers: [{ blocker: "Legacy React order ticket remains toy fill", severity: "WATCH" }]
  };
  cached = { manifest, rows, summary };
  return cached;
}

export function manifestResponse() {
  return loadRun().manifest;
}

export function replayResponse(offset: number, limit: number, stride: number): ReplayResponse {
  const run = loadRun();
  const safeStride = Math.max(1, stride);
  const rows = run.rows.filter((_row, index) => index >= offset && (index - offset) % safeStride === 0).slice(0, limit);
  return {
    run_tag: run.manifest.run_tag,
    symbol: "CCUSDT",
    date: run.manifest.dates[0],
    offset,
    limit,
    stride: safeStride,
    rows_returned: rows.length,
    rows,
    source_parts: [run.manifest.run_tag],
    data_sources: {
      price_book: "Runner events.ndjson",
      factors: "Runner strategy_signal / market_quote",
      join_key: "replay_ts + event_index",
      caveat: "React layout comparison; order ticket is not Runner-owned.",
      price_book_kind: "book_state",
      factor_kind: "strategy signal snapshot"
    }
  };
}

export function summaryResponse() {
  return loadRun().summary;
}
