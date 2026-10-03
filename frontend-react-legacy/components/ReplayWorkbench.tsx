"use client";

import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  ChevronsRight,
  Database,
  Info,
  LineChart,
  Pause,
  Play,
  RotateCcw,
  Send,
  ShoppingCart,
  StepForward,
  TrendingUp,
  Zap
} from "lucide-react";
import katex from "katex";
import type { MouseEvent as ReactMouseEvent, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { askLocalAi, fetchManifest, fetchReplay, fetchSummary } from "../lib/api";
import type {
  BookLevel,
  ManifestResponse,
  MarketInfo,
  OrderSide,
  OrderType,
  ReplayResponse,
  ReplayRow,
  SimOrder,
  SummaryResponse
} from "../lib/types";

const DEFAULT_LIMIT = 3600;
const CHART_HISTORY_EVENTS = 360;
const DEFAULT_CONTEXT_EVENTS = 560;
const ACTIVE_FACTOR_EPS = 1e-9;
const PRICE_CHART_ZOOM_WINDOWS = [120, 240, 360, 560] as const;
type ReplayDataSources = ReplayResponse["data_sources"];

type FactorMeta = {
  key: string;
  label: string;
  group: string;
  formula: string;
  latex?: string;
  read: string;
  source: string;
  caveat?: string;
};

type RankedFactorRow = {
  featureName: string;
  label: string;
  score: number;
  side: string;
  fold: string;
  horizon: string;
  gate: string;
  variants: number;
};

const FACTOR_DEFS: FactorMeta[] = [
  {
    key: "trade_flow_imbalance",
    label: "Trade Flow Imb.",
    group: "Trades",
    formula: "(trade_buy_amount - trade_sell_amount) / max(trade_buy_amount + trade_sell_amount, eps)",
    latex: "\\frac{B_{trade}-S_{trade}}{\\max(B_{trade}+S_{trade},\\epsilon)}",
    read: "Positive means taker buys dominated the matched trade window; negative means taker sells dominated.",
    source: "V10c trade window around the book-update batch."
  },
  {
    key: "queue_imbalance_1",
    label: "Queue Imb. L1",
    group: "Depth",
    formula: "(bid_depth_1 - ask_depth_1) / max(bid_depth_1 + ask_depth_1, eps)",
    latex: "\\frac{D^{bid}_{1}-D^{ask}_{1}}{\\max(D^{bid}_{1}+D^{ask}_{1},\\epsilon)}",
    read: "Top-of-book depth skew. Positive means more visible bid size than ask size at L1.",
    source: "V10c event panel, depth after the update batch."
  },
  {
    key: "queue_imbalance_5",
    label: "Queue Imb. L5",
    group: "Depth",
    formula: "(bid_depth_5 - ask_depth_5) / max(bid_depth_5 + ask_depth_5, eps)",
    latex: "\\frac{D^{bid}_{5}-D^{ask}_{5}}{\\max(D^{bid}_{5}+D^{ask}_{5},\\epsilon)}",
    read: "Five-level depth skew. It is smoother than L1 and less sensitive to a single quote.",
    source: "V10c event panel, summed top-five depth."
  },
  {
    key: "queue_imbalance_25",
    label: "Queue Imb. L25",
    group: "Depth",
    formula: "(bid_depth_25 - ask_depth_25) / max(bid_depth_25 + ask_depth_25, eps)",
    latex: "\\frac{D^{bid}_{25}-D^{ask}_{25}}{\\max(D^{bid}_{25}+D^{ask}_{25},\\epsilon)}",
    read: "Broad visible-book skew. Positive suggests deeper bid support across the sampled ladder.",
    source: "V10c event panel, summed top-25 depth."
  },
  {
    key: "ofi_l1_depth_norm",
    label: "OFI L1 Norm",
    group: "OFI",
    formula: "CKS_L1_OFI(before, after) / max(before_L1_depth, after_L1_depth, eps)",
    latex: "\\frac{OFI^{CKS}_{L1}(book_{t-1},book_t)}{\\max(D_{L1,t-1},D_{L1,t},\\epsilon)}",
    read: "Best-level order-flow imbalance normalized by nearby depth. Positive means bid pressure or ask retreat dominated the update.",
    source: "V10c event-defined CKS OFI."
  },
  {
    key: "mlofi_norm_l1",
    label: "MLOFI L1",
    group: "MLOFI",
    formula: "CKS_OFI(level=1, before, after) / max(before_level_depth, after_level_depth, eps)",
    latex: "\\frac{OFI^{CKS}_{L1}(book_{t-1},book_t)}{\\max(D_{L1,t-1},D_{L1,t},\\epsilon)}",
    read: "Level-1 multi-level OFI member. It reacts quickly but can be noisy.",
    source: "V10c XGH-style MLOFI."
  },
  {
    key: "mlofi_norm_l2",
    label: "MLOFI L2",
    group: "MLOFI",
    formula: "CKS_OFI(level=2, before, after) / max(before_level_depth, after_level_depth, eps)",
    latex: "\\frac{OFI^{CKS}_{L2}(book_{t-1},book_t)}{\\max(D_{L2,t-1},D_{L2,t},\\epsilon)}",
    read: "Second-level pressure. It helps separate touch-only flicker from pressure that reaches just behind the best quote.",
    source: "Event-defined MLOFI panel."
  },
  {
    key: "mlofi_norm_l3",
    label: "MLOFI L3",
    group: "MLOFI",
    formula: "CKS_OFI(level=3, before, after) / max(before_level_depth, after_level_depth, eps)",
    latex: "\\frac{OFI^{CKS}_{L3}(book_{t-1},book_t)}{\\max(D_{L3,t-1},D_{L3,t},\\epsilon)}",
    read: "Third-level pressure. It is a shallow-book bridge between L1 noise and deeper L5/L10 state.",
    source: "Event-defined MLOFI panel."
  },
  {
    key: "mlofi_norm_l5",
    label: "MLOFI L5",
    group: "MLOFI",
    formula: "CKS_OFI(level=5, before, after) / max(before_level_depth, after_level_depth, eps)",
    latex: "\\frac{OFI^{CKS}_{L5}(book_{t-1},book_t)}{\\max(D_{L5,t-1},D_{L5,t},\\epsilon)}",
    read: "Fifth-level pressure. It helps show whether pressure is only at the touch or deeper in the book.",
    source: "V10c XGH-style MLOFI."
  },
  {
    key: "mlofi_norm_l10",
    label: "MLOFI L10",
    group: "MLOFI",
    formula: "CKS_OFI(level=10, before, after) / max(before_level_depth, after_level_depth, eps)",
    latex: "\\frac{OFI^{CKS}_{L10}(book_{t-1},book_t)}{\\max(D_{L10,t-1},D_{L10,t},\\epsilon)}",
    read: "Tenth-level pressure. This was one of the better research diagnostics, but still not a strategy by itself.",
    source: "V10c XGH-style MLOFI."
  },
  {
    key: "mlofi_norm_l25",
    label: "MLOFI L25",
    group: "MLOFI",
    formula: "CKS_OFI(level=25, before, after) / max(before_level_depth, after_level_depth, eps)",
    latex: "\\frac{OFI^{CKS}_{L25}(book_{t-1},book_t)}{\\max(D_{L25,t-1},D_{L25,t},\\epsilon)}",
    read: "Broad visible-book pressure. CCUSDT uses this to inspect whether pressure persists beyond the first few levels.",
    source: "Event-defined MLOFI panel."
  },
  {
    key: "mlofi_roll10_l1",
    label: "MLOFI L1 Roll",
    group: "MLOFI",
    formula: "mean(last 10 event values of mlofi_norm_l1)",
    latex: "\\frac{1}{10}\\sum_{i=0}^{9} MLOFI_{L1,t-i}",
    read: "Event-time smoothed L1 pressure. CCUSDT V3 ranks this family highly, but it still needs cost and control checks.",
    source: "Rolling event buffer over the factor panel."
  },
  {
    key: "mlofi_roll10_l5",
    label: "MLOFI L5 Roll",
    group: "MLOFI",
    formula: "mean(last 10 event values of mlofi_norm_l5)",
    latex: "\\frac{1}{10}\\sum_{i=0}^{9} MLOFI_{L5,t-i}",
    read: "Event-time smoothed L5 pressure. Useful for spotting persistent shallow-to-mid-depth pressure.",
    source: "Rolling event buffer over the factor panel."
  },
  {
    key: "mlofi_roll10_l10",
    label: "MLOFI L10 Roll",
    group: "MLOFI",
    formula: "mean(last 10 event values of mlofi_norm_l10)",
    latex: "\\frac{1}{10}\\sum_{i=0}^{9} MLOFI_{L10,t-i}",
    read: "Event-time smoothed L10 pressure. Useful for seeing whether pressure persists or just flashes.",
    source: "V10c rolling event buffer."
  },
  {
    key: "mlofi_roll10_l25",
    label: "MLOFI L25 Roll",
    group: "MLOFI",
    formula: "mean(last 10 event values of mlofi_norm_l25)",
    latex: "\\frac{1}{10}\\sum_{i=0}^{9} MLOFI_{L25,t-i}",
    read: "Event-time smoothed broad-depth pressure. This is one of the leading CCUSDT V3 replay-inspection factors.",
    source: "Rolling event buffer over the factor panel."
  },
  {
    key: "mlofi_combo",
    label: "MLOFI Combo",
    group: "MLOFI",
    formula: "weighted or fallback mean of MLOFI L1/L2/L3/L5/L10/L25",
    latex: "\\sum_{l\\in\\{1,2,3,5,10,25\\}} w_l\\,MLOFI_l",
    read: "Composite multi-level pressure. If exact trained weights are absent from the replay row, the UI uses an equal-weight inspection proxy.",
    source: "Derived from replay-row MLOFI levels.",
    caveat: "The UI proxy may not match the research fitter's fold-specific weights exactly."
  },
  {
    key: "microprice_dev_bps",
    label: "Micro Dev",
    group: "Price",
    formula: "((microprice - mid_price) / mid_price) * 10000",
    latex: "10{,}000\\cdot\\frac{microprice_t-mid_t}{mid_t}",
    read: "Positive means the size-weighted microprice is above mid, usually because bid-side size is heavier.",
    source: "V10c panel diagnostic; compare against book-state price if the source warning appears."
  },
  {
    key: "queue_depletion_intensity",
    label: "Depletion Int.",
    group: "Events",
    formula: "depletion_total / max(current_depth_25, before_depth_25, eps)",
    latex: "\\frac{Q^{deplete}_t}{\\max(D_{25,t},D_{25,t-1},\\epsilon)}",
    read: "How large the current queue depletion is relative to visible depth.",
    source: "V10c event update classification.",
    caveat: "Execution vs cancellation split is low-confidence on these symbol-days; treat as stress/flow diagnostics."
  },
  {
    key: "replenish_intensity",
    label: "Replenish Int.",
    group: "Events",
    formula: "replenish_total / max(current_depth_25, before_depth_25, eps)",
    latex: "\\frac{Q^{replenish}_t}{\\max(D_{25,t},D_{25,t-1},\\epsilon)}",
    read: "How much size was replenished relative to visible depth.",
    source: "V10c event update classification."
  },
  {
    key: "cancellation_withdrawal_intensity",
    label: "Cancel/Withdraw",
    group: "Events",
    formula: "cancel_total / max(current_depth_25, before_depth_25, eps)",
    latex: "\\frac{Q^{cancel/withdraw}_t}{\\max(D_{25,t},D_{25,t-1},\\epsilon)}",
    read: "Estimated non-execution withdrawal pressure. High values can mean unstable visible liquidity.",
    source: "V10c event update classification.",
    caveat: "Use as a liquidity-risk read, not as a clean cancellation label."
  },
  {
    key: "liquidity_shock_score",
    label: "Liquidity Shock",
    group: "Risk",
    formula: "depletion_total / max(before_depth_25, eps)",
    latex: "\\frac{Q^{deplete}_t}{\\max(D_{25,t-1},\\epsilon)}",
    read: "Large values flag update batches that removed a meaningful share of prior visible depth.",
    source: "V10c event update classification."
  },
  {
    key: "crossed_levels_removed",
    label: "Cross Cleanup",
    group: "Quality",
    formula: "count(levels removed by crossed-book cleanup after applying the event batch)",
    latex: "\\#\\{levels\\ removed\\ by\\ crossed\\ book\\ cleanup_t\\}",
    read: "Non-zero values warn that the reconstructed book needed cleanup; this is a quality/stress flag.",
    source: "book_state plus V10c event diagnostics."
  },
  {
    key: "trade_arrival_alignment",
    label: "Trade Arrival",
    group: "Trades",
    formula: "signed trade arrival alignment around the event window",
    latex: "A^{trade}_t",
    read: "Positive values mean nearby trades line up with the event-side pressure; negative values suggest disagreement.",
    source: "Past-only trade alignment in the fixed event factor panel."
  },
  {
    key: "cross_venue_mlofi_lead_lag",
    label: "Cross-Venue Lead",
    group: "Cross Venue",
    formula: "best aligned cross-venue MLOFI lead/lag value",
    latex: "CV^{MLOFI}_{lead/lag,t}",
    read: "Cross-venue pressure diagnostic where available. Single-market CCUSDT replay may leave this empty.",
    source: "Cross-venue alignment diagnostics where the research run provides them.",
    caveat: "Absent values are displayed as zero for chart stability; do not infer no signal from missing cross-venue rows."
  }
];

const FACTOR_META = Object.fromEntries(FACTOR_DEFS.map((item) => [item.key, item])) as Record<string, FactorMeta>;
const BASE_FACTOR_KEYS = FACTOR_DEFS.map((item) => item.key);

type FactorTransform = "abs" | "pos" | "neg" | "signed_sq";

const DERIVED_PREFIXES: Array<[`${FactorTransform}__`, FactorTransform]> = [
  ["abs__", "abs"],
  ["pos__", "pos"],
  ["neg__", "neg"],
  ["signed_sq__", "signed_sq"]
];

function buildFactorOptions(summary: SummaryResponse | null): FactorMeta[] {
  const keys = new Set<string>();
  for (const row of summary?.factor_ranking ?? []) {
    const key = String(row.feature_name ?? "").trim();
    if (key) keys.add(key);
  }
  for (const key of BASE_FACTOR_KEYS) keys.add(key);
  return [...keys].map(factorMetaFor);
}

function factorMetaFor(key: string): FactorMeta {
  if (FACTOR_META[key]) return FACTOR_META[key];
  const derived = splitDerivedFactor(key);
  if (derived) {
    const base = factorMetaFor(derived.base);
    const transformLabel = transformMeta(derived.transform);
    return {
      key,
      label: `${transformLabel.label} ${base.label}`,
      group: base.group,
      formula: `${transformLabel.formula}(${base.formula})`,
      latex: transformLatex(derived.transform, base.latex ?? base.formula),
      read: `${transformLabel.read} Base read: ${base.read}`,
      source: base.source,
      caveat: base.caveat
    };
  }
  return {
    key,
    label: humanizeFactorKey(key),
    group: factorGroupFromKey(key),
    formula: key,
    read: "No hand-written description has been added yet; use this as a raw replay-row diagnostic.",
    source: "Replay row factors."
  };
}

function splitDerivedFactor(key: string): { transform: FactorTransform; base: string } | null {
  for (const [prefix, transform] of DERIVED_PREFIXES) {
    if (key.startsWith(prefix)) return { transform, base: key.slice(prefix.length) };
  }
  return null;
}

function transformMeta(transform: FactorTransform) {
  switch (transform) {
    case "abs":
      return {
        label: "Abs",
        formula: "abs",
        read: "Absolute-value transform: direction is removed and magnitude is emphasized."
      };
    case "pos":
      return {
        label: "Pos",
        formula: "max(0, x)",
        read: "Positive-part transform: only pressure above zero contributes."
      };
    case "neg":
      return {
        label: "Neg",
        formula: "max(0, -x)",
        read: "Negative-part transform: only pressure below zero contributes after sign flip."
      };
    case "signed_sq":
      return {
        label: "Signed Sq",
        formula: "sign(x) * x^2",
        read: "Signed-square transform: large values are amplified while retaining direction."
      };
  }
}

function transformLatex(transform: FactorTransform, baseLatex: string) {
  switch (transform) {
    case "abs":
      return `\\left|${baseLatex}\\right|`;
    case "pos":
      return `\\max\\left(0,${baseLatex}\\right)`;
    case "neg":
      return `\\max\\left(0,-${baseLatex}\\right)`;
    case "signed_sq":
      return `\\operatorname{sgn}\\left(${baseLatex}\\right)\\cdot\\left(${baseLatex}\\right)^2`;
  }
}

function factorGroupFromKey(key: string) {
  const base = splitDerivedFactor(key)?.base ?? key;
  if (base.includes("mlofi")) return "MLOFI";
  if (base.includes("ofi")) return "OFI";
  if (base.includes("queue")) return "Depth";
  if (base.includes("trade")) return "Trades";
  if (base.includes("microprice")) return "Price";
  if (base.includes("cross_venue")) return "Cross Venue";
  if (base.includes("shock") || base.includes("depletion") || base.includes("replenish") || base.includes("cancellation")) return "Risk";
  return "Custom";
}

function humanizeFactorKey(key: string) {
  return key
    .replace(/__/g, " ")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (value) => value.toUpperCase());
}

export function ReplayWorkbench() {
  const [manifest, setManifest] = useState<ManifestResponse | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [dataSources, setDataSources] = useState<ReplayDataSources | null>(null);
  const [rows, setRows] = useState<ReplayRow[]>([]);
  const [market, setMarket] = useState("ccusdt");
  const [markets, setMarkets] = useState<MarketInfo[]>([
    {
      id: "ccusdt",
      label: "CCUSDT",
      run_tag: "20260517_ccusdt_fixed_factors_v3",
      replay_mode: "factor_panel_only",
      default_symbol: "CCUSDT",
      default_date: "2026-04-29"
    },
    {
      id: "bonk",
      label: "BONK",
      run_tag: "20260514_bonk_v10_stage1_pilot",
      replay_mode: "book_state_plus_factors",
      default_symbol: "BONK1MUSDC",
      default_date: "2026-05-06"
    }
  ]);
  const [symbol, setSymbol] = useState("CCUSDT");
  const [date, setDate] = useState("2026-04-29");
  const [offset, setOffset] = useState(0);
  const [offsetDraft, setOffsetDraft] = useState("0");
  const [stride, setStride] = useState(1);
  const [index, setIndex] = useState(0);
  const [selectedFactor, setSelectedFactor] = useState("mlofi_roll10_l25");
  const [aiFactor, setAiFactor] = useState("mlofi_roll10_l25");
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(18);
  const [qty, setQty] = useState(10);
  const [orderType, setOrderType] = useState<OrderType>("market");
  const [side, setSide] = useState<OrderSide>("buy");
  const [limitPrice, setLimitPrice] = useState("");
  const [orders, setOrders] = useState<SimOrder[]>([]);
  const [error, setError] = useState("");
  const [aiPrompt, setAiPrompt] = useState("请解释当前因子和价格/波动率的关系，重点判断它是领先、同步、滞后，还是只是噪声。");
  const [aiAnswer, setAiAnswer] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");
  const [aiSaveInfo, setAiSaveInfo] = useState("");
  const nextOrderId = useRef(1);
  const pendingJumpIndex = useRef<number | null>(null);

  useEffect(() => {
    fetchManifest(market)
      .then((value) => {
        setManifest(value);
        if (value.markets.length > 0) setMarkets(value.markets);
        if (value.symbols.length > 0) setSymbol(value.symbols[0]);
        if (value.dates.length > 0) setDate(value.dates[0]);
      })
      .catch((err: Error) => setError(err.message));
  }, [market]);

  useEffect(() => {
    let cancelled = false;
    setError("");
    setSummary(null);
    setDataSources(null);
    fetchReplay(market, symbol, date, offset, DEFAULT_LIMIT, stride)
      .then((value) => {
        if (cancelled) return;
        const nextIndex = pendingJumpIndex.current ?? defaultReplayIndex(value.rows, selectedFactor);
        pendingJumpIndex.current = null;
        setRows(value.rows);
        setDataSources(value.data_sources);
        setIndex(Math.min(nextIndex, Math.max(0, value.rows.length - 1)));
        setPlaying(false);
      })
      .catch((err: Error) => setError(err.message));
    fetchSummary(market, symbol, date)
      .then((value) => {
        if (!cancelled) setSummary(value);
      })
      .catch((err: Error) => setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [market, symbol, date, offset, stride]);

  useEffect(() => {
    if (!playing || rows.length === 0) return;
    const id = window.setInterval(() => stepForward(), Math.max(15, 1000 / speed));
    return () => window.clearInterval(id);
  });

  useEffect(() => {
    const topFeature = String(summary?.factor_ranking?.[0]?.feature_name ?? "").trim();
    if (!topFeature) return;
    setSelectedFactor(topFeature);
    setAiFactor(topFeature);
    if (rows.length > 0 && offset === 0) {
      setIndex(defaultReplayIndex(rows, topFeature));
    }
  }, [summary?.run_tag, symbol, date, rows, offset]);

  const current = rows[index];
  const markPrice = current?.mid_price ?? 0;
  const previous = rows[Math.max(0, index - 1)];
  const priceChangeBps = previous && previous.mid_price > 0 ? ((markPrice / previous.mid_price) - 1) * 10000 : 0;
  const visibleWindow = useMemo(
    () => rows.slice(Math.max(0, index - 560), index + 1),
    [rows, index]
  );
  const trailingRows = useMemo(() => rows.slice(Math.max(0, index - 240), index + 1), [rows, index]);
  const hourState = useMemo(() => pickCurrentHour(summary?.state_hourly ?? [], current), [summary, current]);
  const hourQuality = useMemo(() => pickCurrentHour(summary?.quality_hourly ?? [], current), [summary, current]);
  const vol = useMemo(() => buildVolForecast(trailingRows, current), [trailingRows, current]);
  const topFactorRows = useMemo(() => summarizeFactorRanking(summary?.factor_ranking ?? []).slice(0, 8), [summary]);
  const factorOptions = useMemo(() => buildFactorOptions(summary), [summary]);
  const sourceHealth = useMemo(() => buildSourceHealth(current), [current]);
  const factorAnalysis = useMemo(() => buildFactorAnalysis(visibleWindow, selectedFactor), [visibleWindow, selectedFactor]);
  const aiFactorAnalysis = useMemo(() => buildFactorAnalysis(visibleWindow, aiFactor), [visibleWindow, aiFactor]);
  const portfolio = useMemo(() => buildPortfolio(orders, markPrice), [orders, markPrice]);
  const absoluteOffset = offset + index * stride;
  const marketInfo = markets.find((item) => item.id === market);
  const marketLabel = manifest?.market_label ?? marketInfo?.label ?? symbol;
  const qtyLabel = market === "bonk" ? "Qty, BONK1M" : "Qty, units";
  const selectedFactorMeta = factorMetaFor(selectedFactor);
  const aiFactorMeta = factorMetaFor(aiFactor);
  const isFactorPanelReplay = dataSources?.price_book_kind === "factor_panel" || marketInfo?.replay_mode === "factor_panel_only";
  const frameNoun = isFactorPanelReplay ? "frame" : "event";
  const frameNounTitle = isFactorPanelReplay ? "Frame" : "Event";
  const qualityValue = isFactorPanelReplay
    ? "N/A for CC factor panel"
    : String(hourQuality?.quality_tier ?? "N/A");

  function stepForward() {
    setIndex((value) => {
      const next = Math.min(rows.length - 1, value + 1);
      const nextRow = rows[next];
      if (nextRow) processPending(nextRow, next);
      if (next === rows.length - 1) setPlaying(false);
      return next;
    });
  }

  function resetSession() {
    setPlaying(false);
    setIndex(defaultReplayIndex(rows, selectedFactor));
    setOrders([]);
    nextOrderId.current = 1;
  }

  function changeMarket(nextMarket: string) {
    const next = markets.find((item) => item.id === nextMarket);
    setMarket(nextMarket);
    setSymbol(next?.default_symbol ?? "");
    setDate(next?.default_date ?? "");
    setOffset(0);
    setOffsetDraft("0");
    setIndex(0);
    setRows([]);
    setOrders([]);
    setPlaying(false);
    nextOrderId.current = 1;
  }

  function jumpToOffset() {
    const target = Math.max(0, toInt(offsetDraft, offset));
    const requestOffset = Math.max(0, target - CHART_HISTORY_EVENTS);
    const nextIndex = target - requestOffset;
    setPlaying(false);
    if (requestOffset === offset && rows.length > 0) {
      setIndex(Math.min(nextIndex, rows.length - 1));
    } else {
      pendingJumpIndex.current = nextIndex;
      setOffset(requestOffset);
    }
  }

  function processPending(row: ReplayRow, rowIndex: number) {
    setOrders((currentOrders) => {
      return currentOrders.map((order) => {
        if (order.status !== "pending") return order;
        const fillPrice = executablePrice(order, row);
        if (!fillPrice) return order;
        return {
          ...order,
          status: "filled" as const,
          fillPrice,
          fillIndex: rowIndex,
          filledAt: row.timestamp_utc
        };
      });
    });
  }

  function submitOrder() {
    if (!current || qty <= 0) return;
    const parsedLimit = limitPrice ? Number(limitPrice) : null;
    const order: SimOrder = {
      id: nextOrderId.current++,
      side,
      type: orderType,
      qty,
      limitPrice: orderType === "limit" ? parsedLimit : null,
      status: "pending",
      createdAt: current.timestamp_utc,
      createdIndex: index
    };
    const fillPrice = executablePrice(order, current);
    if (fillPrice) {
      setOrders((value) => [{
        ...order,
        status: "filled",
        fillPrice,
        fillIndex: index,
        filledAt: current.timestamp_utc
      }, ...value]);
    } else {
      setOrders((value) => [order, ...value]);
    }
  }

  async function submitAiQuestion() {
    if (!aiPrompt.trim() || aiLoading) return;
    setAiLoading(true);
    setAiError("");
    setAiSaveInfo("");
    try {
      const response = await askLocalAi(aiPrompt, {
        symbol,
        date,
        timestamp: current?.timestamp_utc,
        offset: absoluteOffset,
        selectedFactor: aiFactor,
        factorLabel: factorMetaFor(aiFactor).label,
        factorValue: factorValue(current, aiFactor),
        price: current?.mid_price,
        bestBid: current?.best_bid_price,
        bestAsk: current?.best_ask_price,
        spreadBps: current?.spread_bps,
        volatilityForecastBps: vol.forecastBps,
        realizedVolBps: vol.realizedBps,
        dlogStBps: aiFactorAnalysis.currentDlogBps,
        tickSize: aiFactorAnalysis.tickSize,
        feeHurdleTicks: aiFactorAnalysis.feeTicks,
        meanAbsNextMoveTicks: aiFactorAnalysis.meanAbsNextMoveTicks,
        pAbsMoveGtFee: aiFactorAnalysis.pAbsMoveGtFee,
        pearsonCurrentReturn: aiFactorAnalysis.pearsonCurrentReturn,
        pearsonNextReturn: aiFactorAnalysis.pearsonNextReturn,
        pearsonAbsNextReturn: aiFactorAnalysis.pearsonAbsNextReturn,
        lagCorrs: aiFactorAnalysis.lagCorrs,
        panelMidDeltaBps: sourceHealth.panelDeltaBps,
        dataSources
      });
      setAiAnswer(response.answer || "Local AI returned an empty answer.");
      const saveStatus = response.save_error
        ? `save failed: ${response.save_error}`
        : `saved ${shortId(response.note_id)} / memory used ${response.saved_notes_used ?? 0}`;
      setAiSaveInfo(saveStatus);
    } catch (err) {
      setAiError(err instanceof Error ? err.message : "Local AI request failed");
    } finally {
      setAiLoading(false);
    }
  }

  return (
    <main className="terminal">
      <header className="terminal-topbar">
        <div className="symbol-block">
          <div className="symbol-name">
            <span className="brand-mark">{marketLabel.slice(0, 1)}</span>
            <div>
              <h1>{symbol}</h1>
              <p>{marketLabel} replay / {manifest?.run_tag ?? "loading"}</p>
            </div>
          </div>
          <div className="ticker-price">
            <strong>{fmt(markPrice, 6)}</strong>
            <span className={priceChangeBps >= 0 ? "positive" : "negative"}>{signed(priceChangeBps, 3)} bps</span>
          </div>
        </div>
        <div className="terminal-controls">
          <select value={market} onChange={(event) => changeMarket(event.target.value)} aria-label="Market">
            {markets.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
          <select value={symbol} onChange={(event) => setSymbol(event.target.value)} aria-label="Symbol">
            {(manifest?.symbols ?? [symbol]).map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select value={date} onChange={(event) => setDate(event.target.value)} aria-label="Date">
            {(manifest?.dates ?? [date]).map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <label><span>Cursor {frameNoun}</span><input value={offsetDraft} onChange={(event) => setOffsetDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") jumpToOffset(); }} /></label>
          <button className="go-button" title={`Jump to cursor ${frameNoun}`} onClick={jumpToOffset}>Go</button>
          <label><span>Stride</span><input value={stride} onChange={(event) => setStride(Math.max(1, toInt(event.target.value, 1)))} /></label>
        </div>
      </header>

      {error ? <div className="error-bar">{error}</div> : null}

      <section className="ticker-row">
        <Metric label="Best Bid" value={fmt(current?.best_bid_price, 6)} tone="buy" />
        <Metric label="Best Ask" value={fmt(current?.best_ask_price, 6)} tone="sell" />
        <Metric label="Spread" value={`${fmt(current?.spread_bps, 3)} bps`} tone={asNum(current?.spread_bps) > 3 ? "warn" : "neutral"} />
        <Metric label="Vol Forecast" value={`${fmt(vol.forecastBps, 2)} bps`} tone={vol.forecastBps > 3 ? "warn" : "neutral"} />
        <Metric label="RV Trail" value={`${fmt(vol.realizedBps, 2)} bps`} />
        <Metric label="Quality" value={qualityValue} />
      </section>

      <DataSourceStrip sources={dataSources} health={sourceHealth} absoluteOffset={absoluteOffset} windowOffset={offset} current={current} frameNounTitle={frameNounTitle} />

      <section className="replay-controls">
        <button title="Play" onClick={() => setPlaying(true)} disabled={!rows.length || playing}><Play size={17} /></button>
        <button title="Pause" onClick={() => setPlaying(false)} disabled={!playing}><Pause size={17} /></button>
        <button title="Step" onClick={stepForward} disabled={!rows.length}><StepForward size={17} /></button>
        <button title="Reset" onClick={resetSession}><RotateCcw size={17} /></button>
        <label className="timeline">
          <span>{index + 1}/{rows.length || 0}</span>
          <input type="range" min="0" max={Math.max(0, rows.length - 1)} value={index} onChange={(event) => setIndex(Number(event.target.value))} />
        </label>
        <label className="speed">
          <ChevronsRight size={15} />
          <input type="range" min="1" max="120" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} />
          <span>{speed}x</span>
        </label>
      </section>

      <section className="terminal-grid">
        <section className="terminal-panel chart-panel">
          <PanelTitle icon={<TrendingUp size={16} />} title="Chart" value={current?.timestamp_utc ?? "--"} />
          <ChartToolbar selectedFactor={selectedFactor} factorPanelReplay={isFactorPanelReplay} />
          <PriceChart rows={visibleWindow} current={current} selectedFactor={selectedFactor} factorPanelReplay={isFactorPanelReplay} />
          <VolatilityPanel vol={vol} row={current} hourState={hourState} factorPanelReplay={isFactorPanelReplay} />
        </section>

        <section className="terminal-panel book-panel">
          <PanelTitle icon={<BarChart3 size={16} />} title="Order Book" value={`${fmt(current?.best_bid_price, 6)} / ${fmt(current?.best_ask_price, 6)}`} />
          <OrderBook asks={current?.ask_levels ?? []} bids={current?.bid_levels ?? []} />
          <EventTape rows={visibleWindow} factorPanelReplay={isFactorPanelReplay} />
        </section>

        <section className="terminal-panel trade-panel">
          <PanelTitle icon={<ShoppingCart size={16} />} title={isFactorPanelReplay ? "Replay Sim" : "Trade"} value={isFactorPanelReplay ? "toy fill only" : `${portfolio.side} / ${signedPnl(portfolio.totalPnl, 2)}`} />
          <TradeTicket
            side={side}
            setSide={setSide}
            orderType={orderType}
            setOrderType={setOrderType}
            qty={qty}
            setQty={setQty}
            limitPrice={limitPrice}
            setLimitPrice={setLimitPrice}
            markPrice={markPrice}
            qtyLabel={qtyLabel}
            submitOrder={submitOrder}
            disabled={!current}
            factorPanelReplay={isFactorPanelReplay}
          />
          <div className={`portfolio ${isFactorPanelReplay ? "toy" : ""}`}>
            <Metric label={isFactorPanelReplay ? "Toy Position" : "Position"} value={`${portfolio.side} ${fmt(Math.abs(portfolio.position), 3)}`} tone={portfolio.position === 0 ? "neutral" : portfolio.position > 0 ? "buy" : "sell"} />
            <Metric label={isFactorPanelReplay ? "Toy Entry" : "Avg Entry"} value={portfolio.position === 0 ? "--" : fmt(portfolio.avgEntry, 6)} />
            <Metric label={isFactorPanelReplay ? "Toy Unreal" : "Unreal PnL"} value={signedPnl(portfolio.unrealizedPnl, 2)} tone={pnlTone(portfolio.unrealizedPnl)} />
            <Metric label={isFactorPanelReplay ? "Toy Realized" : "Realized PnL"} value={signedPnl(portfolio.realizedPnl, 2)} tone={pnlTone(portfolio.realizedPnl)} />
            <Metric label={isFactorPanelReplay ? "Toy Total" : "Total PnL"} value={signedPnl(portfolio.totalPnl, 2)} tone={pnlTone(portfolio.totalPnl)} />
          </div>
          <OrderTape orders={orders} markPrice={markPrice} factorPanelReplay={isFactorPanelReplay} />
        </section>

        <section className="terminal-panel assistant-panel">
          <PanelTitle icon={<Bot size={16} />} title="AI Assistant" value={aiFactorMeta.label} />
          <AiAssistant
            prompt={aiPrompt}
            setPrompt={setAiPrompt}
            answer={aiAnswer}
            error={aiError}
            saveInfo={aiSaveInfo}
            loading={aiLoading}
            submit={submitAiQuestion}
            analysis={aiFactorAnalysis}
            factorKey={aiFactor}
            setFactorKey={setAiFactor}
            factorOptions={factorOptions}
            currentFactorValue={factorValue(current, aiFactor)}
          />
        </section>

        <section className="terminal-panel factors-panel">
          <PanelTitle icon={<Activity size={16} />} title="Factors" value={String(current?.factors.execute_cancel_confidence ?? "--")} />
          <FactorBoard
            row={current}
            rows={visibleWindow}
            hourState={hourState}
            selected={selectedFactor}
            setSelected={setSelectedFactor}
            factorOptions={factorOptions}
            factorPanelReplay={isFactorPanelReplay}
          />
        </section>

        <section className="terminal-panel factor-detail-panel">
          <PanelTitle icon={<LineChart size={16} />} title="Factor Detail" value={selectedFactorMeta.label} />
          <FactorInspector rows={visibleWindow} row={current} selected={selectedFactor} sources={dataSources} analysis={factorAnalysis} />
        </section>

        <section className="terminal-panel research-panel">
          <PanelTitle icon={<Zap size={16} />} title="Research" value={`${topFactorRows.length} features / ${summary?.factor_ranking.length ?? 0} rows`} />
          <ResearchTables factors={topFactorRows} blockers={summary?.blockers ?? []} paths={summary?.path_summary ?? []} />
        </section>
      </section>
    </main>
  );
}

function executablePrice(order: SimOrder, row: ReplayRow): number | null {
  if (order.type === "market") return order.side === "buy" ? row.best_ask_price : row.best_bid_price;
  if (!order.limitPrice || order.limitPrice <= 0) return null;
  if (order.side === "buy" && order.limitPrice >= row.best_ask_price) return row.best_ask_price;
  if (order.side === "sell" && order.limitPrice <= row.best_bid_price) return row.best_bid_price;
  return null;
}

function PanelTitle({ icon, title, value }: { icon: ReactNode; title: string; value: string }) {
  return (
    <div className="panel-title">
      <div>{icon}<span>{title}</span></div>
      <strong>{value}</strong>
    </div>
  );
}

function Metric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "buy" | "sell" | "warn" }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

type SourceHealth = {
  panelDeltaBps: number;
  panelDeltaTicks: number;
  status: "ok" | "warn";
};

function DataSourceStrip({
  sources,
  health,
  absoluteOffset,
  windowOffset,
  current,
  frameNounTitle
}: {
  sources: ReplayDataSources | null;
  health: SourceHealth;
  absoluteOffset: number;
  windowOffset: number;
  current?: ReplayRow;
  frameNounTitle: string;
}) {
  const isSnapshotFrame = asBool(current?.factors.is_snapshot_batch);
  const batchRows = asNum(current?.factors.batch_rows);
  const frameSource = isSnapshotFrame
    ? `snapshot / ${fmt(batchRows, 0)} raw rows`
    : batchRows > 0 ? `update batch / ${fmt(batchRows, 0)} rows` : "--";
  return (
    <section className={`source-strip ${health.status}`}>
      <div>
        <Database size={15} />
        <span>Price/book</span>
        <strong>{sources?.price_book_kind ?? "--"}</strong>
      </div>
      <div>
        <Activity size={15} />
        <span>Factors</span>
        <strong>{sources?.factor_kind ?? "--"}</strong>
      </div>
      <div>
        {health.status === "warn" ? <AlertTriangle size={15} /> : <Info size={15} />}
        <span>Panel mid delta</span>
        <strong>{fmt(health.panelDeltaBps, 3)} bps / {fmt(health.panelDeltaTicks, 2)} ticks</strong>
      </div>
      <div>
        <Info size={15} />
        <span>{frameNounTitle} source</span>
        <strong>{frameSource}</strong>
      </div>
      <div>
        <ChevronsRight size={15} />
        <span>Window offset</span>
        <strong>{windowOffset.toLocaleString()}</strong>
      </div>
      <div>
        <ChevronsRight size={15} />
        <span>Cursor {frameNounTitle.toLowerCase()}</span>
        <strong>{absoluteOffset.toLocaleString()} / #{current?.event_index ?? "--"}</strong>
      </div>
    </section>
  );
}

function ChartToolbar({ selectedFactor, factorPanelReplay }: { selectedFactor: string; factorPanelReplay: boolean }) {
  const active = factorMetaFor(selectedFactor).label;
  return (
    <div className="chart-toolbar">
      <div className="chart-tabs">
        <button className="active">Replay</button>
        <button>Book</button>
        <button>Factors</button>
      </div>
      <div className="chart-tools">
        <span>{factorPanelReplay ? "Factor panel" : "Book replay"}</span>
        <span>{factorPanelReplay ? "Snapshot frame" : "Event step"}</span>
        <strong>{active}</strong>
      </div>
    </div>
  );
}

function PriceChart({
  rows,
  current,
  selectedFactor,
  factorPanelReplay
}: {
  rows: ReplayRow[];
  current?: ReplayRow;
  selectedFactor: string;
  factorPanelReplay: boolean;
}) {
  const [zoomEvents, setZoomEvents] = useState<number>(CHART_HISTORY_EVENTS);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const width = 1120;
  const height = 520;
  const pad = { left: 56, right: 86, top: 26, bottom: 42 };
  const volumeHeight = 92;
  const chartRows = useMemo(() => {
    if (zoomEvents >= rows.length) return rows;
    return rows.slice(Math.max(0, rows.length - zoomEvents));
  }, [rows, zoomEvents]);
  const bars = useMemo(() => buildBars(chartRows, 150, !factorPanelReplay), [chartRows, factorPanelReplay]);
  const all = chartRows.flatMap((row) => [row.mid_price, row.microprice]);
  if (chartRows.length === 0 || all.length === 0) {
    return <svg className="price-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="empty price chart" />;
  }
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom - volumeHeight;
  const volumeTop = pad.top + chartH + 18;
  const y = (value: number) => pad.top + chartH - ((value - min) / span) * chartH;
  const x = (idx: number) => pad.left + (idx / Math.max(1, bars.length - 1)) * chartW;
  const barStep = chartW / Math.max(1, bars.length);
  const bodyW = Math.max(2, Math.min(7, barStep * 0.58));
  const rowX = (idx: number) => pad.left + (idx / Math.max(1, chartRows.length - 1)) * chartW;
  const midPath = stepLinePath(chartRows.map((row, idx) => [rowX(idx), y(row.mid_price)]));
  const microPath = stepLinePath(chartRows.map((row, idx) => [rowX(idx), y(row.microprice)]));
  const lastY = current ? y(current.mid_price) : pad.top + chartH / 2;
  const maxVolume = Math.max(1, ...bars.map((bar) => bar.volume));
  const hasTradeNotional = chartRows.some((row) => Math.abs(asNum(row.factors.trade_notional_quote)) > 0);
  const activityLabel = factorPanelReplay
    ? "Activity proxy (snapshot depth)"
    : hasTradeNotional ? "Trade notional" : "Activity proxy (depth)";
  const quoteStats = quoteRunStats(chartRows);
  const frameNoun = factorPanelReplay ? "frame" : "event";
  const frameNounPlural = factorPanelReplay ? "frames" : "events";
  const grid = Array.from({ length: 5 }, (_, idx) => {
    const gy = pad.top + (idx / 4) * chartH;
    const value = max - (idx / 4) * span;
    return { gy, value };
  });
  const activeHoverIndex = hoverIndex === null
    ? chartRows.length - 1
    : clamp(hoverIndex, 0, chartRows.length - 1);
  const activeRow = chartRows[activeHoverIndex] ?? current ?? chartRows[chartRows.length - 1];
  const activeX = rowX(activeHoverIndex);
  const activeY = y(activeRow.mid_price);
  const tooltipX = activeX > width - 278 ? activeX - 252 : activeX + 14;
  const tooltipY = activeY > height - 154 ? activeY - 126 : activeY + 14;
  const xTicks = Array.from(new Set([
    0,
    Math.floor((chartRows.length - 1) / 2),
    chartRows.length - 1
  ])).filter((idx) => idx >= 0);
  const factorLabel = factorMetaFor(selectedFactor).label;
  const activeFactorValue = factorValue(activeRow, selectedFactor);
  const lastRow = chartRows[chartRows.length - 1];

  function onMouseMove(event: ReactMouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const viewX = (event.clientX - rect.left) * (width / rect.width);
    if (viewX < pad.left || viewX > pad.left + chartW) {
      setHoverIndex(null);
      return;
    }
    const nextIndex = Math.round(((viewX - pad.left) / chartW) * Math.max(1, chartRows.length - 1));
    setHoverIndex(clamp(nextIndex, 0, chartRows.length - 1));
  }

  return (
    <div className="price-chart-shell">
      <div className="chart-readout">
        {factorPanelReplay ? <span className="chart-caveat">CC factor panel: snapshot-frame replay, no queue-position fill evidence</span> : null}
        <div className="chart-zoom">
          <span>Zoom</span>
          {PRICE_CHART_ZOOM_WINDOWS.map((value) => (
            <button
              className={Math.min(value, rows.length) === Math.min(zoomEvents, rows.length) ? "active" : ""}
              key={value}
              onClick={() => setZoomEvents(value)}
            >
              {value}
            </button>
          ))}
          <button className={zoomEvents >= rows.length ? "active" : ""} onClick={() => setZoomEvents(Number.MAX_SAFE_INTEGER)}>All</button>
        </div>
        <span>min <strong>{fmt(min, 6)}</strong></span>
        <span>max <strong>{fmt(max, 6)}</strong></span>
        <span>last <strong>{fmt(lastRow?.mid_price, 6)}</strong></span>
        {quoteStats && quoteStats.events >= 8 ? (
          <span className="quote-run-readout">
            quote stable <strong>{quoteStats.events} {frameNounPlural} / {formatDuration(quoteStats.seconds)}</strong>
            {" "}depth Δ <strong>{signed(quoteStats.bidDelta, 1)} bid / {signed(quoteStats.askDelta, 1)} ask</strong>
            {" "}micro Δ <strong>{signed(quoteStats.microDeltaBps, 4)} bps</strong>
          </span>
        ) : null}
        <span className="hover-readout">hover <strong>{shortTime(activeRow)} / {fmt(activeRow.mid_price, 6)}</strong></span>
      </div>
      <svg
        className="price-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="market replay price line"
        onMouseMove={onMouseMove}
        onMouseLeave={() => setHoverIndex(null)}
      >
        <rect className="chart-bg" x="0" y="0" width={width} height={height} rx="6" />
        <line className="axis-line" x1={pad.left} x2={pad.left} y1={pad.top} y2={volumeTop + volumeHeight} />
        <line className="axis-line" x1={pad.left} x2={pad.left + chartW} y1={volumeTop + volumeHeight} y2={volumeTop + volumeHeight} />
        {grid.map((line) => (
          <g key={line.gy}>
            <line className="grid-line" x1={pad.left} x2={pad.left + chartW} y1={line.gy} y2={line.gy} />
            <text className="axis-label" x={width - 10} y={line.gy + 4} textAnchor="end">{fmt(line.value, 6)}</text>
          </g>
        ))}
        {xTicks.map((idx) => (
          <g key={`x-${idx}`}>
            <line className="grid-line vertical" x1={rowX(idx)} x2={rowX(idx)} y1={pad.top} y2={volumeTop + volumeHeight} />
            <text className="axis-label" x={rowX(idx)} y={height - 14} textAnchor={idx === 0 ? "start" : idx === chartRows.length - 1 ? "end" : "middle"}>
              {shortTime(chartRows[idx])}
            </text>
          </g>
        ))}
        {bars.map((bar, idx) => {
          const cx = x(idx);
          const volume = (bar.volume / maxVolume) * (volumeHeight - 20);
          return (
            <g key={`${bar.start}-${idx}`} className="activity-bar">
              <rect x={cx - bodyW / 2} y={volumeTop + volumeHeight - volume} width={bodyW} height={volume} rx="1" />
            </g>
          );
        })}
        <path d={midPath} className="mid-line step" />
        <path d={microPath} className="micro-line step" />
        <line className="last-line" x1={pad.left} x2={pad.left + chartW} y1={lastY} y2={lastY} />
        <rect className="last-price-box" x={width - 76} y={lastY - 12} width="68" height="24" rx="4" />
        <text className="last-price-text" x={width - 42} y={lastY + 4} textAnchor="middle">{fmt(current?.mid_price, 6)}</text>
        <text className="legend mid" x={pad.left + 8} y="24">MID</text>
        <text className="legend micro" x={pad.left + 54} y="24">MICRO</text>
        <text className="legend activity" x={pad.left + 128} y="24">{factorPanelReplay ? "SNAPSHOT FRAMES" : "EVENT STEP"}</text>
        <line className="volume-separator" x1={pad.left} x2={pad.left + chartW} y1={volumeTop - 10} y2={volumeTop - 10} />
        <text className="axis-label" x={pad.left + 8} y={volumeTop + 12}>{activityLabel}</text>
        <g className="crosshair">
          <line x1={activeX} x2={activeX} y1={pad.top} y2={volumeTop + volumeHeight} />
          <line x1={pad.left} x2={pad.left + chartW} y1={activeY} y2={activeY} />
          <circle cx={activeX} cy={activeY} r="4" />
          <rect className="crosshair-box" x={tooltipX} y={tooltipY} width="238" height="104" rx="6" />
          <text x={tooltipX + 12} y={tooltipY + 21}>cursor {frameNoun} {activeHoverIndex + 1}/{chartRows.length} / {shortTime(activeRow)}</text>
          <text x={tooltipX + 12} y={tooltipY + 42}>mid {fmt(activeRow.mid_price, 6)} / micro {fmt(activeRow.microprice, 6)}</text>
          <text x={tooltipX + 12} y={tooltipY + 63}>spread {fmt(activeRow.spread_bps, 3)} bps</text>
          <text x={tooltipX + 12} y={tooltipY + 84}>{factorLabel}: {fmt(activeFactorValue, 4)}</text>
        </g>
        <rect className="chart-hitbox" x={pad.left} y={pad.top} width={chartW} height={chartH + volumeHeight + 18} />
      </svg>
    </div>
  );
}

function VolatilityPanel({ vol, row, hourState, factorPanelReplay }: { vol: VolForecast; row?: ReplayRow; hourState?: Record<string, unknown>; factorPanelReplay: boolean }) {
  const ccNa = "N/A for CC factor panel";
  return (
    <div className="vol-panel">
      <div className="vol-main">
        <span>{factorPanelReplay ? "Frame Activity" : "Volatility Forecast"}</span>
        <strong>{fmt(vol.forecastBps, 2)} bps</strong>
        <em>{vol.regime}</em>
      </div>
      <div className="vol-grid">
        <Metric label="Trailing RV" value={`${fmt(vol.realizedBps, 2)} bps`} />
        <Metric label="Shock Adj" value={`${fmt(vol.shockAdj, 2)}x`} tone={vol.shockAdj > 1.3 ? "warn" : "neutral"} />
        <Metric label="Micro Dev" value={`${fmt(row?.factors.microprice_dev_bps, 3)} bps`} />
        <Metric label="Flow Abs" value={fmt(Math.abs(asNum(row?.factors.trade_flow_imbalance)), 3)} />
        <Metric label="Hour Spread" value={factorPanelReplay ? ccNa : `${fmt(asNum(hourState?.spread_bps_mean), 3)} bps`} />
        <Metric label="Fill Realism" value={factorPanelReplay ? ccNa : fmt(asNum(hourState?.fill_realism_score_mean), 3)} />
      </div>
    </div>
  );
}

type BookDepthRow = {
  level: BookLevel;
  cumulative: number;
};

function OrderBook({ asks, bids }: { asks: BookLevel[]; bids: BookLevel[] }) {
  const topAsks = cumulativeDepthRows(asks.slice(0, 16)).reverse();
  const topBids = cumulativeDepthRows(bids.slice(0, 16));
  const maxCumulative = Math.max(1, ...topAsks.concat(topBids).map((row) => row.cumulative));
  const bestAsk = asks[0]?.price ?? 0;
  const bestBid = bids[0]?.price ?? 0;
  const spread = bestAsk && bestBid ? (bestAsk - bestBid) : 0;
  const mid = bestAsk && bestBid ? (bestAsk + bestBid) * 0.5 : 0;
  const spreadBps = bestAsk && bestBid ? Math.log(bestAsk / bestBid) * 10_000 : 0;
  return (
    <div className="book">
      <div className="book-mode-row">
        <span><i className="ask-mark" /> asks</span>
        <span><i className="bid-mark" /> bids</span>
        <strong>cumulative depth</strong>
      </div>
      <div className="book-head"><span>Price</span><span>Amount</span><span>Total</span></div>
      {topAsks.map((row) => <BookRow key={`a-${row.level.price}`} row={row} max={maxCumulative} side="ask" />)}
      <div className="book-mid">
        <strong>{fmt(mid, 6)}</strong>
        <span>{fmt(spread, 6)} spread / {fmt(spreadBps, 2)} bps</span>
      </div>
      {topBids.map((row) => <BookRow key={`b-${row.level.price}`} row={row} max={maxCumulative} side="bid" />)}
    </div>
  );
}

function BookRow({ row, max, side }: { row: BookDepthRow; max: number; side: "bid" | "ask" }) {
  const { level, cumulative } = row;
  const width = `${Math.max(2, (cumulative / max) * 100)}%`;
  return (
    <div className={`book-row ${side}`}>
      <span className="book-bar" style={{ width }} />
      <span>{fmt(level.price, 6)}</span>
      <strong>{fmt(level.amount, 3)}</strong>
      <em>{fmt(cumulative, 3)}</em>
    </div>
  );
}

function TradeTicket(props: {
  side: OrderSide;
  setSide: (side: OrderSide) => void;
  orderType: OrderType;
  setOrderType: (type: OrderType) => void;
  qty: number;
  setQty: (value: number) => void;
  limitPrice: string;
  setLimitPrice: (value: string) => void;
  markPrice: number;
  qtyLabel: string;
  submitOrder: () => void;
  disabled: boolean;
  factorPanelReplay: boolean;
}) {
  const buyLabel = props.factorPanelReplay ? "Toy Buy" : "Buy / Long";
  const sellLabel = props.factorPanelReplay ? "Toy Sell" : "Sell / Short";
  const sendLabel = props.factorPanelReplay
    ? `Add ${props.side === "buy" ? "Toy Buy" : "Toy Sell"}`
    : `Send ${props.side === "buy" ? "Buy / Long" : "Sell / Short"}`;
  return (
    <>
      {props.factorPanelReplay ? (
        <div className="toy-fill-caveat">
          CCUSDT is factor-panel replay only. This ticket records toy fills for visual what-if inspection, not executable queue-position evidence.
        </div>
      ) : null}
      <div className="segmented side-tabs">
        <button className={props.side === "buy" ? "active buy" : ""} onClick={() => props.setSide("buy")}>{buyLabel}</button>
        <button className={props.side === "sell" ? "active sell" : ""} onClick={() => props.setSide("sell")}>{sellLabel}</button>
      </div>
      <div className="side-meaning">
        {props.factorPanelReplay
          ? "Toy fills cross the displayed panel bid/ask for replay inspection only; they are not evidence of executable fills."
          : "Buy crosses the ask and adds/keeps long exposure; Sell crosses the bid and adds/keeps short exposure. Profit/loss is shown separately below, not implied by green/red side labels."}
      </div>
      <div className="segmented">
        <button className={props.orderType === "market" ? "active" : ""} onClick={() => props.setOrderType("market")}>Market</button>
        <button className={props.orderType === "limit" ? "active" : ""} onClick={() => props.setOrderType("limit")}>Limit</button>
      </div>
      <label className="ticket-field">
        <span>{props.qtyLabel}</span>
        <input value={props.qty} onChange={(event) => props.setQty(Number(event.target.value))} />
      </label>
      <label className="ticket-field">
        <span>Limit</span>
        <input
          value={props.limitPrice}
          onChange={(event) => props.setLimitPrice(event.target.value)}
          placeholder={fmt(props.markPrice, 6)}
          disabled={props.orderType === "market"}
        />
      </label>
      <button className={`submit-order ${props.side}`} onClick={props.submitOrder} disabled={props.disabled}>
        <ShoppingCart size={16} />
        {sendLabel}
      </button>
    </>
  );
}

function EventTape({ rows, factorPanelReplay }: { rows: ReplayRow[]; factorPanelReplay: boolean }) {
  const items = rows.slice(-16).reverse();
  return (
    <div className="event-tape">
      <div className="event-tape-title">
        <span>{factorPanelReplay ? "Latest Frames" : "Latest Events"}</span>
        <strong>price Δ / taker flow</strong>
      </div>
      {items.map((row, idx) => {
        const prev = rows[rows.length - 1 - idx - 1];
        const change = prev?.mid_price ? (row.mid_price / prev.mid_price - 1) * 10000 : 0;
        const flow = asNum(row.factors.trade_flow_imbalance);
        const flowLabel = flow > 0 ? "taker buy" : flow < 0 ? "taker sell" : "flat";
        return (
          <div className={`event-row ${change >= 0 ? "up" : "down"}`} key={`${row.timestamp}-${idx}`}>
            <span>{fmt(row.mid_price, 6)}</span>
            <strong>{signed(change, 2)}</strong>
            <em className={flow > 0 ? "flow-buy" : flow < 0 ? "flow-sell" : ""}>{flowLabel} {fmt(Math.abs(flow), 3)}</em>
            <time>{row.timestamp_utc.slice(11, 19)}</time>
          </div>
        );
      })}
    </div>
  );
}

function FactorBoard({
  row,
  rows,
  hourState,
  selected,
  setSelected,
  factorOptions,
  factorPanelReplay
}: {
  row?: ReplayRow;
  rows: ReplayRow[];
  hourState?: Record<string, unknown>;
  selected: string;
  setSelected: (key: string) => void;
  factorOptions: FactorMeta[];
  factorPanelReplay: boolean;
}) {
  if (!row) return <div className="empty">No replay rows loaded</div>;
  const boardOptions = factorOptions.slice(0, 22);
  const ccNa = "N/A for CC factor panel";
  return (
    <div className="factor-list">
      {boardOptions.map((meta) => {
        const key = meta.key;
        const value = factorValue(row, key);
        const numeric = asNum(value);
        const series = factorSeries(rows, key);
        return (
          <button className={`factor-row ${selected === key ? "selected" : ""}`} key={key} onClick={() => setSelected(key)} title={meta.formula}>
            <span>{meta.label}</span>
            <Sparkline values={series} />
            <strong className={numeric > 0 ? "pos" : numeric < 0 ? "neg" : ""}>{fmt(value, 4)}</strong>
          </button>
        );
      })}
      <div className="factor-state">
        <Metric label="Hour Potential" value={factorPanelReplay ? ccNa : fmt(asNum(hourState?.net_potential_mean), 4)} />
        <Metric label="Flow Align" value={factorPanelReplay ? ccNa : fmt(asNum(hourState?.trade_flow_alignment_rate), 3)} />
        <Metric label="Fill Realism" value={factorPanelReplay ? ccNa : fmt(asNum(hourState?.fill_realism_score_mean), 3)} />
      </div>
    </div>
  );
}

function FactorInspector({
  rows,
  row,
  selected,
  sources,
  analysis
}: {
  rows: ReplayRow[];
  row?: ReplayRow;
  selected: string;
  sources: ReplayDataSources | null;
  analysis: FactorAnalysis;
}) {
  const meta = factorMetaFor(selected);
  const factorValues = factorSeries(rows, selected);
  const priceValues = rows.map((item) => item.mid_price);
  const currentReturnBps = currentReturnsBps(rows);
  const currentValue = factorValue(row, selected);
  const stats = seriesStats(factorValues);

  return (
    <div className="factor-inspector">
      <div className="factor-detail-head">
        <div>
          <span>{meta.group}</span>
          <strong>{meta.label}</strong>
        </div>
        <div className="factor-stats">
          <Metric label="Current" value={fmt(currentValue, 4)} tone={asNum(currentValue) > 0 ? "buy" : asNum(currentValue) < 0 ? "sell" : "neutral"} />
          <Metric label="Win Max |F|" value={fmt(stats.maxAbs, 4)} tone={stats.maxAbs > ACTIVE_FACTOR_EPS ? "warn" : "neutral"} />
          <Metric label="Win Min F" value={fmt(stats.min, 4)} tone={stats.min < 0 ? "sell" : "neutral"} />
          <Metric label="Win Max F" value={fmt(stats.max, 4)} tone={stats.max > 0 ? "buy" : "neutral"} />
          <Metric label="dlogS_t" value={`${signed(analysis.currentDlogBps, 3)} bps`} tone={analysis.currentDlogBps > 0 ? "buy" : analysis.currentDlogBps < 0 ? "sell" : "neutral"} />
          <Metric label="rho(F,dlogS_t)" value={fmt(analysis.pearsonCurrentReturn, 3)} />
          <Metric label="rho(F,R+1)" value={fmt(analysis.pearsonNextReturn, 3)} />
          <Metric label="rho(F,|R+1|)" value={fmt(analysis.pearsonAbsNextReturn, 3)} />
          <Metric label="Avg |R+1|" value={`${fmt(analysis.meanAbsNextMoveTicks, 2)}t`} tone={analysis.meanAbsNextMoveTicks < analysis.feeTicks ? "warn" : "neutral"} />
          <Metric label="Hist P>|fee|" value={`${fmt(analysis.pAbsMoveGtFee * 100, 1)}%`} tone={analysis.pAbsMoveGtFee < 0.35 ? "warn" : "neutral"} />
        </div>
      </div>
      <div className="correlation-lens">
        <NormalizedOverlayChart priceValues={priceValues} factorValues={factorValues} factorLabel={meta.label} />
        <CorrelationScatter factorValues={factorValues.slice(0, -1)} returns={nextReturnsTicks(rows, analysis.tickSize)} rho={analysis.pearsonNextReturn} />
        <LagCorrelationBars items={analysis.lagCorrs} />
      </div>
      <div className="paired-charts">
        <SeriesChart title="dlogS_t bps" values={currentReturnBps} color="price" digits={3} zeroLine />
        <SeriesChart title={meta.label} values={factorValues} color={asNum(currentValue) >= 0 ? "buy" : "sell"} digits={4} zeroLine />
      </div>
      <div className="factor-explain">
        <div>
          <span>Formula</span>
          <MathFormula latex={meta.latex ?? meta.formula} fallback={meta.formula} />
        </div>
        <div>
          <span>Read</span>
          <p>{meta.read}</p>
          <p className="cost-read">
            dlogS_t = ln(S_t / S_t-1) * 10000 is the same-event price move. A strong rho(F,dlogS_t) can mean price impact or price-discovery synchronization; tradability still needs R+1/lead-lag after costs. Hist P&gt;|fee| is the visible-window frequency of abs(next-event move in ticks) greater than {fmt(analysis.feeTicks, 1)} ticks, not a model probability.
          </p>
        </div>
        <div>
          <span>Source</span>
          <p>{meta.source} Price/book path: {sources?.price_book ?? "--"}. Factor path: {sources?.factors ?? "--"}.</p>
        </div>
        {meta.caveat ? (
          <div className="factor-caveat">
            <AlertTriangle size={14} />
            <p>{meta.caveat}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function MathFormula({ latex, fallback }: { latex: string; fallback: string }) {
  let html = "";
  try {
    html = katex.renderToString(latex, {
      displayMode: true,
      throwOnError: false,
      strict: "ignore",
      output: "html"
    });
  } catch {
    html = "";
  }
  if (!html) return <code>{fallback}</code>;
  return <div className="math-formula" dangerouslySetInnerHTML={{ __html: html }} />;
}

function NormalizedOverlayChart({
  priceValues,
  factorValues,
  factorLabel
}: {
  priceValues: number[];
  factorValues: number[];
  factorLabel: string;
}) {
  const width = 680;
  const height = 220;
  const pad = { left: 40, right: 28, top: 24, bottom: 24 };
  const priceZ = zscores(logValues(priceValues));
  const factorZ = zscores(factorValues);
  const all = priceZ.concat(factorZ).filter(Number.isFinite);
  const min = Math.min(-2.5, ...all);
  const max = Math.max(2.5, ...all);
  const span = max - min || 1;
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const x = (idx: number) => pad.left + (idx / Math.max(1, priceValues.length - 1)) * chartW;
  const y = (value: number) => pad.top + chartH - ((value - min) / span) * chartH;
  const pricePoints = priceZ.map((value, idx) => `${x(idx).toFixed(2)},${y(value).toFixed(2)}`).join(" ");
  const factorPoints = factorZ.map((value, idx) => `${x(idx).toFixed(2)},${y(value).toFixed(2)}`).join(" ");
  const zeroY = y(0);
  return (
    <div className="analysis-card overlay-card">
      <div className="analysis-title">
        <span>Normalized Overlay</span>
        <strong>log price z</strong>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Normalized price factor overlay">
        <rect className="chart-bg" x="0" y="0" width={width} height={height} rx="4" />
        <line className="zero-line" x1={pad.left} x2={pad.left + chartW} y1={zeroY} y2={zeroY} />
        {[-2, -1, 1, 2].map((tick) => (
          <line key={tick} className="grid-line" x1={pad.left} x2={pad.left + chartW} y1={y(tick)} y2={y(tick)} />
        ))}
        <polyline className="overlay-line price" points={pricePoints} />
        <polyline className="overlay-line factor" points={factorPoints} />
        <text className="legend mid" x={pad.left + 8} y="20">log price z</text>
        <text className="legend factor" x={pad.left + 112} y="20">{factorLabel} z</text>
      </svg>
    </div>
  );
}

function CorrelationScatter({ factorValues, returns, rho }: { factorValues: number[]; returns: number[]; rho: number }) {
  const width = 330;
  const height = 220;
  const pad = { left: 40, right: 18, top: 24, bottom: 32 };
  const pairs = pairFinite(zscores(factorValues), returns);
  const sampled = downsamplePairs(pairs, 220);
  const xs = sampled.map((item) => item[0]);
  const ys = sampled.map((item) => item[1]);
  const minX = Math.min(-2.5, ...xs);
  const maxX = Math.max(2.5, ...xs);
  const minY = Math.min(-2.5, ...ys);
  const maxY = Math.max(2.5, ...ys);
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const x = (value: number) => pad.left + ((value - minX) / (maxX - minX || 1)) * chartW;
  const y = (value: number) => pad.top + chartH - ((value - minY) / (maxY - minY || 1)) * chartH;
  return (
    <div className="analysis-card">
      <div className="analysis-title">
        <span>Scatter</span>
        <strong>rho {fmt(rho, 3)}</strong>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Factor next return scatter">
        <rect className="chart-bg" x="0" y="0" width={width} height={height} rx="4" />
        <line className="zero-line" x1={pad.left} x2={pad.left + chartW} y1={y(0)} y2={y(0)} />
        <line className="zero-line" x1={x(0)} x2={x(0)} y1={pad.top} y2={pad.top + chartH} />
        {sampled.map((item, idx) => (
          <circle key={idx} cx={x(item[0])} cy={y(item[1])} r="2.2" />
        ))}
        <text className="axis-label" x={pad.left} y={height - 8}>factor z</text>
        <text className="axis-label" x={width - 96} y={height - 8}>next move ticks</text>
      </svg>
    </div>
  );
}

function LagCorrelationBars({ items }: { items: LagCorr[] }) {
  return (
    <div className="analysis-card lag-card">
      <div className="analysis-title">
        <span>Lead/Lag Corr</span>
        <strong>Pearson rho</strong>
      </div>
      <div className="lag-bars">
        {items.map((item) => {
          const width = `${Math.min(100, Math.abs(item.corr) * 100)}%`;
          return (
            <div className="lag-row" key={item.lag}>
              <span>R+{item.lag}</span>
              <div><i className={item.corr >= 0 ? "pos" : "neg"} style={{ width }} /></div>
              <strong>{fmt(item.corr, 3)}</strong>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AiAssistant(props: {
  prompt: string;
  setPrompt: (value: string) => void;
  answer: string;
  error: string;
  saveInfo: string;
  loading: boolean;
  submit: () => void;
  analysis: FactorAnalysis;
  factorKey: string;
  setFactorKey: (value: string) => void;
  factorOptions: FactorMeta[];
  currentFactorValue: unknown;
}) {
  return (
    <div className="ai-assistant">
      <label className="ai-factor-select">
        <span>AI factor</span>
        <select value={props.factorKey} onChange={(event) => props.setFactorKey(event.target.value)}>
          {props.factorOptions.map((item) => (
            <option key={item.key} value={item.key}>{item.group} / {item.label}</option>
          ))}
        </select>
        <strong>{fmt(props.currentFactorValue, 5)}</strong>
      </label>
      <div className="ai-hurdle">
        <Metric label="Fee Hurdle" value={`${fmt(props.analysis.feeTicks, 1)} ticks`} tone="warn" />
        <Metric label="Mean |Next|" value={`${fmt(props.analysis.meanAbsNextMoveTicks, 2)} ticks`} tone={props.analysis.meanAbsNextMoveTicks < props.analysis.feeTicks ? "warn" : "neutral"} />
        <Metric label="Hist >Fee" value={`${fmt(props.analysis.pAbsMoveGtFee * 100, 1)}%`} tone={props.analysis.pAbsMoveGtFee < 0.35 ? "warn" : "neutral"} />
      </div>
      <textarea
        value={props.prompt}
        onChange={(event) => props.setPrompt(event.target.value)}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key === "Enter") props.submit();
        }}
      />
      <button className="ai-submit" onClick={props.submit} disabled={props.loading}>
        <Send size={14} />
        {props.loading ? "Thinking" : "Ask Local AI"}
      </button>
      {props.saveInfo ? <div className="ai-save-info">{props.saveInfo}</div> : null}
      {props.error ? <div className="ai-error">{props.error}</div> : null}
      <AiAnswer answer={props.answer} />
    </div>
  );
}

function AiAnswer({ answer }: { answer: string }) {
  const text = answer
    ? answer
    : "本地 AI 会拿当前 replay、因子、相关性、波动率和 2 tick fee hurdle 做结构化解释。";
  return (
    <div className="ai-answer">
      {parseAiMarkdown(text).map((block, idx) => <AiBlockView block={block} key={idx} />)}
    </div>
  );
}

type AiBlock =
  | { kind: "heading"; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "math"; latex: string }
  | { kind: "code"; text: string }
  | { kind: "table"; rows: string[][] };

function AiBlockView({ block }: { block: AiBlock }) {
  if (block.kind === "heading") {
    return <h3><InlineMathText text={block.text} /></h3>;
  }
  if (block.kind === "list") {
    return (
      <ul>
        {block.items.map((item, idx) => <li key={idx}><InlineMathText text={item} /></li>)}
      </ul>
    );
  }
  if (block.kind === "math") {
    return <MathDisplay latex={block.latex} />;
  }
  if (block.kind === "code") {
    return <pre>{block.text}</pre>;
  }
  if (block.kind === "table") {
    return (
      <div className="ai-table-wrap">
        <table>
          <tbody>
            {block.rows.map((row, rowIdx) => (
              <tr key={rowIdx}>
                {row.map((cell, cellIdx) => <td key={cellIdx}><InlineMathText text={cell} /></td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return <p><InlineMathText text={block.text} /></p>;
}

function InlineMathText({ text }: { text: string }) {
  return (
    <>
      {splitMathText(text).map((part, idx) => part.kind === "math"
        ? <MathInline latex={part.value} key={idx} />
        : <span key={idx}>{part.value}</span>)}
    </>
  );
}

function MathDisplay({ latex }: { latex: string }) {
  try {
    const html = katex.renderToString(latex, {
      displayMode: true,
      throwOnError: false,
      strict: "ignore",
      output: "html"
    });
    return <div className="ai-display-math" dangerouslySetInnerHTML={{ __html: html }} />;
  } catch {
    return <pre>{latex}</pre>;
  }
}

function MathInline({ latex }: { latex: string }) {
  try {
    const html = katex.renderToString(latex, {
      displayMode: false,
      throwOnError: false,
      strict: "ignore",
      output: "html"
    });
    return <span className="ai-math" dangerouslySetInnerHTML={{ __html: html }} />;
  } catch {
    return <code>{latex}</code>;
  }
}

function SeriesChart({ title, values, color, digits, zeroLine = false }: { title: string; values: number[]; color: "price" | "buy" | "sell"; digits: number; zeroLine?: boolean }) {
  const width = 520;
  const height = 210;
  const pad = { left: 44, right: 64, top: 22, bottom: 24 };
  const finite = values.filter(Number.isFinite);
  if (finite.length < 2) {
    return <div className="series-chart"><span>{title}</span><svg viewBox={`0 0 ${width} ${height}`} /></div>;
  }
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const span = max - min || 1;
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const x = (idx: number) => pad.left + (idx / Math.max(1, values.length - 1)) * chartW;
  const y = (value: number) => pad.top + chartH - ((value - min) / span) * chartH;
  const points = values.map((value, idx) => `${x(idx).toFixed(2)},${y(value).toFixed(2)}`).join(" ");
  const last = finite[finite.length - 1];
  const zeroY = y(0);
  return (
    <div className="series-chart">
      <span>{title}</span>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
        <rect className="chart-bg" x="0" y="0" width={width} height={height} rx="4" />
        {[0, 0.5, 1].map((tick) => {
          const gy = pad.top + tick * chartH;
          const value = max - tick * span;
          return (
            <g key={tick}>
              <line className="grid-line" x1={pad.left} x2={pad.left + chartW} y1={gy} y2={gy} />
              <text className="axis-label" x={width - 6} y={gy + 4}>{fmt(value, digits)}</text>
            </g>
          );
        })}
        {zeroLine && min < 0 && max > 0 ? <line className="zero-line" x1={pad.left} x2={pad.left + chartW} y1={zeroY} y2={zeroY} /> : null}
        <polyline points={points} className={`series-line ${color}`} />
        <text className="last-price-text dark" x={width - 34} y={y(last) + 4} textAnchor="middle">{fmt(last, digits)}</text>
      </svg>
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  const width = 114;
  const height = 26;
  if (values.length < 2) return <svg className="spark" viewBox={`0 0 ${width} ${height}`} />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((value, idx) => {
    const x = (idx / Math.max(1, values.length - 1)) * width;
    const y = height - ((value - min) / span) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg className="spark" viewBox={`0 0 ${width} ${height}`}>
      <polyline points={points} />
    </svg>
  );
}

function OrderTape({ orders, markPrice, factorPanelReplay }: { orders: SimOrder[]; markPrice: number; factorPanelReplay: boolean }) {
  return (
    <div className="orders">
      <div className="orders-head">
        <span>ID</span>
        <span>Side</span>
        <span>Type</span>
        <span>Status</span>
        <span>Fill</span>
        <span>Mark PnL</span>
      </div>
      {orders.slice(0, 10).map((order) => (
        <div className={`order-row ${order.side}`} key={order.id}>
          <span>#{order.id}</span>
          <span>{factorPanelReplay ? (order.side === "buy" ? "Toy Buy" : "Toy Sell") : (order.side === "buy" ? "Buy/Long" : "Sell/Short")}</span>
          <span>{order.type}</span>
          <strong>{order.status}</strong>
          <span>{order.fillPrice ? fmt(order.fillPrice, 6) : "--"}</span>
          <em className={pnlTone(orderMarkPnl(order, markPrice))}>{order.fillPrice ? signedPnl(orderMarkPnl(order, markPrice), 2) : "--"}</em>
        </div>
      ))}
    </div>
  );
}

function ResearchTables({ factors, blockers, paths }: { factors: RankedFactorRow[]; blockers: Record<string, unknown>[]; paths: Record<string, unknown>[] }) {
  return (
    <div className="research-grid">
      <div>
        <h2>Top Factors</h2>
        {factors.map((row) => (
          <div className="research-row factor-rank" key={row.featureName} title={row.featureName}>
            <span>{row.label}</span>
            <strong>{fmt(row.score, 3)}</strong>
            <em>{row.side}</em>
            <small>{row.fold} / h{row.horizon} / {row.variants}x</small>
          </div>
        ))}
      </div>
      <div>
        <h2>Path / Stability Reads</h2>
        {paths.slice(0, 8).map((row, idx) => (
          <div className="research-row" key={`${row.anchor_type ?? row.feature_name ?? row.group_value}-${idx}`}>
            <span>{researchPathName(row)}</span>
            <strong>{fmt(researchPathScore(row), 3)}</strong>
            <em>{researchPathMeta(row)}</em>
          </div>
        ))}
      </div>
      <div>
        <h2>Blockers</h2>
        {blockers.map((row, idx) => (
          <div className="research-row blocker" key={`${row.blocker}-${idx}`}>
            <span>{String(row.blocker ?? row.severity ?? "--")}</span>
            <strong>{String(row.severity ?? "--")}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

type VolForecast = {
  realizedBps: number;
  forecastBps: number;
  shockAdj: number;
  regime: "calm" | "active" | "shock";
};

type LagCorr = {
  lag: number;
  corr: number;
};

type FactorAnalysis = {
  pearsonLogPrice: number;
  pearsonCurrentReturn: number;
  pearsonNextReturn: number;
  pearsonAbsNextReturn: number;
  currentDlogBps: number;
  tickSize: number;
  feeTicks: number;
  meanAbsNextMoveTicks: number;
  medianAbsNextMoveTicks: number;
  pAbsMoveGtFee: number;
  lagCorrs: LagCorr[];
};

type OhlcBar = {
  start: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

type QuoteRunStats = {
  events: number;
  seconds: number;
  bidDelta: number;
  askDelta: number;
  microDeltaBps: number;
};

type PortfolioState = {
  position: number;
  avgEntry: number;
  realizedPnl: number;
  unrealizedPnl: number;
  totalPnl: number;
  side: "Flat" | "Long" | "Short";
};

function buildPortfolio(orders: SimOrder[], markPrice: number): PortfolioState {
  let position = 0;
  let avgEntry = 0;
  let realizedPnl = 0;
  const fills = orders
    .filter((order) => order.status === "filled" && Number.isFinite(order.fillPrice ?? NaN))
    .slice()
    .reverse();

  for (const order of fills) {
    const fillPrice = order.fillPrice ?? 0;
    const qty = Math.max(0, order.qty);
    if (qty === 0 || fillPrice <= 0) continue;

    if (order.side === "buy") {
      if (position >= 0) {
        const nextPosition = position + qty;
        avgEntry = nextPosition > 0 ? ((avgEntry * position) + (fillPrice * qty)) / nextPosition : 0;
        position = nextPosition;
      } else {
        const shortSize = Math.abs(position);
        const closing = Math.min(shortSize, qty);
        realizedPnl += (avgEntry - fillPrice) * closing;
        const remainder = qty - closing;
        if (remainder > 0) {
          position = remainder;
          avgEntry = fillPrice;
        } else if (closing === shortSize) {
          position = 0;
          avgEntry = 0;
        } else {
          position += closing;
        }
      }
    } else {
      if (position <= 0) {
        const shortSize = Math.abs(position);
        const nextShortSize = shortSize + qty;
        avgEntry = nextShortSize > 0 ? ((avgEntry * shortSize) + (fillPrice * qty)) / nextShortSize : 0;
        position = -nextShortSize;
      } else {
        const closing = Math.min(position, qty);
        realizedPnl += (fillPrice - avgEntry) * closing;
        const remainder = qty - closing;
        if (remainder > 0) {
          position = -remainder;
          avgEntry = fillPrice;
        } else if (closing === position) {
          position = 0;
          avgEntry = 0;
        } else {
          position -= closing;
        }
      }
    }
  }

  const unrealizedPnl = position > 0
    ? (markPrice - avgEntry) * position
    : position < 0
      ? (avgEntry - markPrice) * Math.abs(position)
      : 0;
  return {
    position,
    avgEntry,
    realizedPnl,
    unrealizedPnl,
    totalPnl: realizedPnl + unrealizedPnl,
    side: position > 0 ? "Long" : position < 0 ? "Short" : "Flat"
  };
}

function orderMarkPnl(order: SimOrder, markPrice: number) {
  if (order.status !== "filled" || !order.fillPrice || !Number.isFinite(markPrice)) return 0;
  return order.side === "buy"
    ? (markPrice - order.fillPrice) * order.qty
    : (order.fillPrice - markPrice) * order.qty;
}

function splitMathText(value: string): Array<{ kind: "text" | "math"; value: string }> {
  const parts: Array<{ kind: "text" | "math"; value: string }> = [];
  const pattern = /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+?\$)/g;
  let cursor = 0;
  for (const match of value.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > cursor) parts.push({ kind: "text", value: value.slice(cursor, start) });
    parts.push({ kind: "math", value: unwrapMathDelimiter(match[0]) });
    cursor = start + match[0].length;
  }
  if (cursor < value.length) parts.push({ kind: "text", value: value.slice(cursor) });
  return parts.length ? parts : [{ kind: "text", value }];
}

function parseAiMarkdown(value: string): AiBlock[] {
  const lines = value.replace(/\r\n/g, "\n").split("\n");
  const blocks: AiBlock[] = [];
  let idx = 0;

  while (idx < lines.length) {
    const line = lines[idx];
    const trimmed = line.trim();
    if (!trimmed) {
      idx += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const code: string[] = [];
      idx += 1;
      while (idx < lines.length && !lines[idx].trim().startsWith("```")) {
        code.push(lines[idx]);
        idx += 1;
      }
      blocks.push({ kind: "code", text: code.join("\n") });
      idx += idx < lines.length ? 1 : 0;
      continue;
    }

    if (trimmed.startsWith("$$") || trimmed.startsWith("\\[")) {
      const { latex, nextIndex } = collectDisplayMath(lines, idx);
      blocks.push({ kind: "math", latex });
      idx = nextIndex;
      continue;
    }

    const heading = trimmed.match(/^#{1,4}\s+(.+)$/);
    if (heading) {
      blocks.push({ kind: "heading", text: cleanMarkdownInline(heading[1]) });
      idx += 1;
      continue;
    }

    if (isTableLine(trimmed)) {
      const tableLines: string[] = [];
      while (idx < lines.length && isTableLine(lines[idx].trim())) {
        tableLines.push(lines[idx].trim());
        idx += 1;
      }
      const rows = tableLines
        .filter((item) => !/^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$/.test(item))
        .map(parseTableRow)
        .filter((row) => row.length > 0);
      if (rows.length) blocks.push({ kind: "table", rows });
      continue;
    }

    if (isListLine(trimmed)) {
      const items: string[] = [];
      while (idx < lines.length && isListLine(lines[idx].trim())) {
        items.push(cleanMarkdownInline(lines[idx].trim().replace(/^([-*+]|\d+[.)])\s+/, "")));
        idx += 1;
      }
      blocks.push({ kind: "list", items });
      continue;
    }

    const paragraph: string[] = [];
    while (idx < lines.length) {
      const next = lines[idx].trim();
      if (!next || next.startsWith("```") || next.startsWith("$$") || next.startsWith("\\[") || /^#{1,4}\s+/.test(next) || isListLine(next) || isTableLine(next)) {
        break;
      }
      paragraph.push(next);
      idx += 1;
    }
    blocks.push({ kind: "paragraph", text: cleanMarkdownInline(paragraph.join(" ")) });
  }

  return blocks.length ? blocks : [{ kind: "paragraph", text: value }];
}

function collectDisplayMath(lines: string[], start: number) {
  const first = lines[start].trim();
  const dollar = first.startsWith("$$");
  const endToken = dollar ? "$$" : "\\]";
  const startToken = dollar ? "$$" : "\\[";
  const firstBody = first.slice(startToken.length);
  if (firstBody.endsWith(endToken) && firstBody.length > endToken.length) {
    return { latex: firstBody.slice(0, -endToken.length).trim(), nextIndex: start + 1 };
  }
  const body: string[] = [firstBody];
  let idx = start + 1;
  while (idx < lines.length) {
    const current = lines[idx].trim();
    if (current.endsWith(endToken)) {
      body.push(current.slice(0, -endToken.length));
      idx += 1;
      break;
    }
    body.push(lines[idx]);
    idx += 1;
  }
  return { latex: body.join("\n").trim(), nextIndex: idx };
}

function isListLine(value: string) {
  return /^([-*+]|\d+[.)])\s+/.test(value);
}

function isTableLine(value: string) {
  return value.includes("|") && value.split("|").length >= 3;
}

function parseTableRow(value: string) {
  return value
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cleanMarkdownInline(cell.trim()))
    .filter(Boolean);
}

function cleanMarkdownInline(value: string) {
  return value
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}

function unwrapMathDelimiter(value: string) {
  if (value.startsWith("$$") && value.endsWith("$$")) return value.slice(2, -2);
  if (value.startsWith("\\[") && value.endsWith("\\]")) return value.slice(2, -2);
  if (value.startsWith("\\(") && value.endsWith("\\)")) return value.slice(2, -2);
  if (value.startsWith("$") && value.endsWith("$")) return value.slice(1, -1);
  return value;
}

function cumulativeDepthRows(levels: BookLevel[]): BookDepthRow[] {
  let cumulative = 0;
  return levels.map((level) => {
    cumulative += Math.max(0, level.amount);
    return { level, cumulative };
  });
}

function buildBars(rows: ReplayRow[], targetBars: number, useTradeNotional = true): OhlcBar[] {
  if (rows.length === 0) return [];
  const step = Math.max(1, Math.ceil(rows.length / targetBars));
  const bars: OhlcBar[] = [];
  for (let start = 0; start < rows.length; start += step) {
    const chunk = rows.slice(start, start + step).filter((row) => Number.isFinite(row.mid_price));
    if (chunk.length === 0) continue;
    const mids = chunk.map((row) => row.mid_price);
    const volume = chunk.reduce((sum, row) => {
      const tradeNotional = Math.abs(asNum(row.factors.trade_notional_quote));
      if (useTradeNotional && tradeNotional > 0) return sum + tradeNotional;
      return sum + Math.max(0, row.best_bid_amount + row.best_ask_amount) * row.mid_price;
    }, 0);
    bars.push({
      start: chunk[0].timestamp,
      open: chunk[0].mid_price,
      high: Math.max(...mids),
      low: Math.min(...mids),
      close: chunk[chunk.length - 1].mid_price,
      volume
    });
  }
  return bars;
}

function quoteRunStats(rows: ReplayRow[]): QuoteRunStats | null {
  if (rows.length < 2) return null;
  const last = rows[rows.length - 1];
  let startIdx = rows.length - 1;
  while (startIdx > 0) {
    const prev = rows[startIdx - 1];
    if (prev.best_bid_price !== last.best_bid_price || prev.best_ask_price !== last.best_ask_price) break;
    startIdx -= 1;
  }
  const first = rows[startIdx];
  const events = rows.length - startIdx;
  if (events < 2) return null;
  const seconds = Math.max(0, (last.timestamp - first.timestamp) / 1_000_000);
  const microDeltaBps = first.microprice > 0 && last.microprice > 0
    ? Math.log(last.microprice / first.microprice) * 10_000
    : 0;
  return {
    events,
    seconds,
    bidDelta: last.best_bid_amount - first.best_bid_amount,
    askDelta: last.best_ask_amount - first.best_ask_amount,
    microDeltaBps
  };
}

function stepLinePath(points: number[][]) {
  if (points.length === 0) return "";
  const [[firstX, firstY], ...rest] = points;
  const commands = [`M ${firstX.toFixed(2)} ${firstY.toFixed(2)}`];
  let lastY = firstY;
  for (const [xValue, yValue] of rest) {
    commands.push(`H ${xValue.toFixed(2)}`, `V ${yValue.toFixed(2)}`);
    lastY = yValue;
  }
  if (points.length === 1) commands.push(`h 0.01`);
  void lastY;
  return commands.join(" ");
}

function movingAveragePoints(values: number[], windowSize: number, x: (idx: number) => number, y: (value: number) => number) {
  return values.map((_, idx) => {
    const slice = values.slice(Math.max(0, idx - windowSize + 1), idx + 1);
    const mean = slice.reduce((sum, value) => sum + value, 0) / slice.length;
    return `${x(idx).toFixed(2)},${y(mean).toFixed(2)}`;
  }).join(" ");
}

function buildVolForecast(rows: ReplayRow[], current?: ReplayRow): VolForecast {
  const returns = [];
  for (let idx = 1; idx < rows.length; idx++) {
    const prev = rows[idx - 1].mid_price;
    const next = rows[idx].mid_price;
    if (prev > 0 && next > 0) returns.push(Math.log(next / prev) * 10000);
  }
  const realizedBps = stddev(returns.slice(-120));
  const flow = Math.abs(asNum(current?.factors.trade_flow_imbalance));
  const shock = Math.abs(asNum(current?.factors.liquidity_shock_score));
  const spread = Math.max(0, asNum(current?.spread_bps));
  const microDev = Math.abs(asNum(current?.factors.microprice_dev_bps));
  const mlofi = Math.abs(asNum(current?.factors.mlofi_roll10_l10));
  const shockAdj = 1 + Math.min(0.9, shock * 12) + Math.min(0.35, flow * 0.18) + Math.min(0.25, mlofi * 0.2) + Math.min(0.2, spread / 12);
  const warmupBaseline = Math.max(0.18, spread * 0.28, microDev * 0.22);
  const baseVol = returns.length >= 10 ? realizedBps : warmupBaseline;
  const forecastBps = baseVol * shockAdj;
  const regime = forecastBps > 4 ? "shock" : forecastBps > 1.7 ? "active" : "calm";
  return { realizedBps, forecastBps, shockAdj, regime };
}

function buildFactorAnalysis(rows: ReplayRow[], selected: string): FactorAnalysis {
  const factorValues = factorSeries(rows, selected);
  const priceValues = rows.map((row) => row.mid_price);
  const logPriceValues = logValues(priceValues);
  const currentRetBps = currentReturnsBps(rows);
  const tickSize = inferTickSize(rows);
  const nextRetBps = nextReturnsBps(rows);
  const nextTicks = nextReturnsTicks(rows, tickSize);
  const absNextTicks = nextTicks.map(Math.abs);
  const feeTicks = 2;
  return {
    pearsonLogPrice: corr(factorValues, logPriceValues),
    pearsonCurrentReturn: corr(factorValues, currentRetBps),
    pearsonNextReturn: corr(factorValues.slice(0, -1), nextRetBps),
    pearsonAbsNextReturn: corr(factorValues.slice(0, -1), nextRetBps.map(Math.abs)),
    currentDlogBps: currentRetBps[currentRetBps.length - 1] ?? 0,
    tickSize,
    feeTicks,
    meanAbsNextMoveTicks: mean(absNextTicks),
    medianAbsNextMoveTicks: median(absNextTicks),
    pAbsMoveGtFee: absNextTicks.length ? absNextTicks.filter((value) => value > feeTicks).length / absNextTicks.length : 0,
    lagCorrs: [1, 3, 5, 10, 20, 40].map((lag) => ({
      lag,
      corr: corr(factorValues.slice(0, -lag), returnsTicksAtLag(rows, tickSize, lag))
    }))
  };
}

function buildSourceHealth(current?: ReplayRow): SourceHealth {
  const panelDeltaBps = asNum(current?.factors.panel_mid_delta_bps);
  const panelDeltaTicks = asNum(current?.factors.panel_mid_delta_ticks_est);
  const status = Math.abs(panelDeltaTicks) > 1.25 || Math.abs(panelDeltaBps) > 0.8 ? "warn" : "ok";
  return { panelDeltaBps, panelDeltaTicks, status };
}

function defaultReplayIndex(rows: ReplayRow[], factorKey: string) {
  if (rows.length === 0) return 0;
  const fallback = Math.max(0, Math.min(rows.length - 1, DEFAULT_CONTEXT_EVENTS - 1));
  const start = Math.min(rows.length - 1, Math.max(0, CHART_HISTORY_EVENTS));
  let bestIndex = fallback;
  let bestAbs = 0;
  for (let idx = start; idx < rows.length; idx++) {
    const value = Math.abs(factorValue(rows[idx], factorKey));
    if (value > bestAbs) {
      bestAbs = value;
      bestIndex = idx;
    }
  }
  return bestAbs > ACTIVE_FACTOR_EPS ? bestIndex : fallback;
}

function factorSeries(rows: ReplayRow[], key: string) {
  return rows.map((row) => factorValue(row, key));
}

function factorValue(row: ReplayRow | undefined, key: string): number {
  if (!row) return 0;
  const direct = row.factors[key];
  if (direct !== undefined && direct !== null) return asNum(direct);

  const derived = splitDerivedFactor(key);
  if (derived) {
    const base = factorValue(row, derived.base);
    switch (derived.transform) {
      case "abs":
        return Math.abs(base);
      case "pos":
        return Math.max(0, base);
      case "neg":
        return Math.max(0, -base);
      case "signed_sq":
        return Math.sign(base) * base * base;
    }
  }

  if (key === "mlofi_combo") {
    const levels = ["mlofi_norm_l1", "mlofi_norm_l2", "mlofi_norm_l3", "mlofi_norm_l5", "mlofi_norm_l10", "mlofi_norm_l25"]
      .map((item) => asNum(row.factors[item]))
      .filter(Number.isFinite);
    return levels.length ? mean(levels) : 0;
  }

  return 0;
}

function seriesStats(values: number[]) {
  const finite = values.filter(Number.isFinite);
  if (finite.length === 0) return { min: 0, max: 0, maxAbs: 0 };
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const maxAbs = Math.max(...finite.map((value) => Math.abs(value)));
  return { min, max, maxAbs };
}

function summarizeFactorRanking(rows: Record<string, unknown>[]): RankedFactorRow[] {
  const grouped = new Map<string, RankedFactorRow>();
  for (const row of rows) {
    const featureName = String(row.feature_name ?? "").trim();
    if (!featureName) continue;
    const current = grouped.get(featureName);
    const score = asNum(row.score);
    const next: RankedFactorRow = {
      featureName,
      label: factorMetaFor(featureName).label,
      score,
      side: String(row.side ?? "--"),
      fold: String(row.fold ?? "--"),
      horizon: String(row.horizon_events ?? "--"),
      gate: String(row.gate ?? "--"),
      variants: (current?.variants ?? 0) + 1
    };
    if (!current || score > current.score) {
      grouped.set(featureName, next);
    } else {
      grouped.set(featureName, { ...current, variants: next.variants });
    }
  }
  return [...grouped.values()].sort((a, b) => b.score - a.score);
}

function researchPathName(row: Record<string, unknown>) {
  const feature = String(row.feature_name ?? "").trim();
  if (feature) return factorMetaFor(feature).label;
  return String(row.anchor_type ?? row.group_value ?? row.group_scope ?? "--");
}

function researchPathScore(row: Record<string, unknown>) {
  return asNum(
    row.avg_net_bps_mean
    ?? row.net_bps_mean
    ?? row.side_return_bps_mean
    ?? row.drawup_drawdown_asymmetry_bps_mean
    ?? row.favorable_minus_adverse_rate
  );
}

function researchPathMeta(row: Record<string, unknown>) {
  const execution = String(row.execution_model ?? "").trim();
  if (execution) return execution;
  const groupScope = String(row.group_scope ?? "").trim();
  const groupValue = String(row.group_value ?? "").trim();
  const horizon = String(row.horizon_events ?? "").trim();
  if (groupScope || groupValue || horizon) {
    return [groupScope, groupValue, horizon ? `h${horizon}` : ""].filter(Boolean).join(" / ");
  }
  return String(row.fold ?? "--");
}

function nextReturnsBps(rows: ReplayRow[]) {
  const out: number[] = [];
  for (let idx = 0; idx < rows.length - 1; idx++) {
    const price = rows[idx].mid_price;
    const next = rows[idx + 1].mid_price;
    out.push(price > 0 && next > 0 ? Math.log(next / price) * 10_000 : 0);
  }
  return out;
}

function currentReturnsBps(rows: ReplayRow[]) {
  if (rows.length === 0) return [];
  const out = [0];
  for (let idx = 1; idx < rows.length; idx++) {
    const prev = rows[idx - 1].mid_price;
    const price = rows[idx].mid_price;
    out.push(prev > 0 && price > 0 ? Math.log(price / prev) * 10_000 : 0);
  }
  return out;
}

function nextReturnsTicks(rows: ReplayRow[], tickSize: number) {
  return returnsTicksAtLag(rows, tickSize, 1);
}

function returnsTicksAtLag(rows: ReplayRow[], tickSize: number, lag: number) {
  const out: number[] = [];
  for (let idx = 0; idx < rows.length - lag; idx++) {
    out.push(tickSize > 0 ? (rows[idx + lag].mid_price - rows[idx].mid_price) / tickSize : 0);
  }
  return out;
}

function inferTickSize(rows: ReplayRow[]) {
  const diffs = rows
    .slice(1)
    .map((row, idx) => Math.abs(row.mid_price - rows[idx].mid_price))
    .filter((value) => Number.isFinite(value) && value > 0);
  if (diffs.length === 0) return 0.001;
  return Math.max(0.000001, Math.min(...diffs));
}

function zscores(values: number[]) {
  const finite = values.filter(Number.isFinite);
  const avg = mean(finite);
  const sd = stddev(finite);
  return values.map((value) => sd > 0 && Number.isFinite(value) ? (value - avg) / sd : 0);
}

function logValues(values: number[]) {
  return values.map((value) => value > 0 && Number.isFinite(value) ? Math.log(value) : 0);
}

function pairFinite(xs: number[], ys: number[]) {
  const n = Math.min(xs.length, ys.length);
  const pairs: Array<[number, number]> = [];
  for (let idx = 0; idx < n; idx++) {
    if (Number.isFinite(xs[idx]) && Number.isFinite(ys[idx])) pairs.push([xs[idx], ys[idx]]);
  }
  return pairs;
}

function downsamplePairs(values: Array<[number, number]>, max: number) {
  if (values.length <= max) return values;
  const step = values.length / max;
  return Array.from({ length: max }, (_, idx) => values[Math.floor(idx * step)]);
}

function corr(xs: number[], ys: number[]) {
  const n = Math.min(xs.length, ys.length);
  if (n < 3) return 0;
  const pairs = pairFinite(xs.slice(0, n), ys.slice(0, n));
  if (pairs.length < 3) return 0;
  const meanX = pairs.reduce((sum, item) => sum + item[0], 0) / pairs.length;
  const meanY = pairs.reduce((sum, item) => sum + item[1], 0) / pairs.length;
  let cov = 0;
  let varX = 0;
  let varY = 0;
  for (const [x, y] of pairs) {
    cov += (x - meanX) * (y - meanY);
    varX += (x - meanX) ** 2;
    varY += (y - meanY) ** 2;
  }
  const denom = Math.sqrt(varX * varY);
  return denom > 0 ? cov / denom : 0;
}

function stddev(values: number[]) {
  if (values.length < 2) return 0;
  const avg = mean(values);
  const variance = values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

function mean(values: number[]) {
  const finite = values.filter(Number.isFinite);
  return finite.length ? finite.reduce((sum, value) => sum + value, 0) / finite.length : 0;
}

function median(values: number[]) {
  const finite = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (finite.length === 0) return 0;
  const mid = Math.floor(finite.length / 2);
  return finite.length % 2 ? finite[mid] : (finite[mid - 1] + finite[mid]) * 0.5;
}

function pickCurrentHour(rows: Record<string, unknown>[], current?: ReplayRow) {
  if (!current) return undefined;
  const hour = current.timestamp_utc.slice(0, 13) + ":00:00Z";
  return rows.find((row) => row.hour_utc === hour);
}

function asNum(value: unknown): number {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function asBool(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return value.toLowerCase() === "true";
  if (typeof value === "number") return value !== 0;
  return false;
}

function fmt(value: unknown, digits = 2): string {
  const numeric = asNum(value);
  if (!Number.isFinite(numeric)) return "--";
  if (Math.abs(numeric) >= 1000) return numeric.toLocaleString(undefined, { maximumFractionDigits: digits });
  return numeric.toFixed(digits);
}

function signed(value: number, digits = 2) {
  return `${value >= 0 ? "+" : ""}${fmt(value, digits)}`;
}

function signedPnl(value: number, digits = 2) {
  return `${signed(value, digits)} quote`;
}

function pnlTone(value: number): "neutral" | "buy" | "sell" | "warn" {
  if (value > 0) return "buy";
  if (value < 0) return "sell";
  return "neutral";
}

function toInt(value: string, fallback: number) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function shortTime(row?: ReplayRow) {
  return row?.timestamp_utc?.slice(11, 19) ?? "--";
}

function formatDuration(seconds: number) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0s";
  if (seconds < 90) return `${fmt(seconds, seconds < 10 ? 1 : 0)}s`;
  return `${fmt(seconds / 60, 1)}m`;
}

function shortId(value?: string) {
  return value ? `#${value.slice(0, 8)}` : "#unsaved";
}
