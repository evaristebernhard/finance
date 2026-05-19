export type BookLevel = {
  price: number;
  amount: number;
};

export type ReplayRow = {
  event_index: number;
  timestamp: number;
  local_timestamp: number;
  timestamp_utc: string;
  best_bid_price: number;
  best_bid_amount: number;
  best_ask_price: number;
  best_ask_amount: number;
  mid_price: number;
  spread_bps: number;
  microprice: number;
  bid_levels: BookLevel[];
  ask_levels: BookLevel[];
  factors: Record<string, number | string | boolean | null>;
};

export type ReplayResponse = {
  run_tag: string;
  symbol: string;
  date: string;
  offset: number;
  limit: number;
  stride: number;
  rows_returned: number;
  rows: ReplayRow[];
  source_parts: string[];
  data_sources: {
    price_book: string;
    factors: string;
    join_key: string;
    caveat: string;
    price_book_kind: string;
    factor_kind: string;
  };
};

export type MarketInfo = {
  id: string;
  label: string;
  run_tag: string;
  replay_mode: "book_state_plus_factors" | "factor_panel_only";
  default_symbol: string;
  default_date: string;
};

export type ManifestResponse = {
  market: string;
  market_label: string;
  run_tag: string;
  replay_mode: "book_state_plus_factors" | "factor_panel_only";
  markets: MarketInfo[];
  symbols: string[];
  dates: string[];
  replay_files: Record<string, unknown>[];
  quality_daily: Record<string, unknown>[];
  artifacts: string[];
};

export type SummaryResponse = {
  run_tag: string;
  symbol: string;
  date: string;
  quality_hourly: Record<string, unknown>[];
  state_hourly: Record<string, unknown>[];
  path_hourly: Record<string, unknown>[];
  path_summary: Record<string, unknown>[];
  factor_ranking: Record<string, unknown>[];
  blockers: Record<string, unknown>[];
};

export type LocalAiResponse = {
  answer: string;
  model?: string;
  note_id?: string;
  saved_notes_used?: number;
  save_error?: string;
};

export type OrderSide = "buy" | "sell";
export type OrderType = "market" | "limit";
export type OrderStatus = "pending" | "filled" | "rejected";

export type SimOrder = {
  id: number;
  side: OrderSide;
  type: OrderType;
  qty: number;
  limitPrice: number | null;
  status: OrderStatus;
  createdAt: string;
  createdIndex: number;
  filledAt?: string;
  fillIndex?: number;
  fillPrice?: number;
};
