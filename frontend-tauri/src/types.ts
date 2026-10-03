export type RunEntry = {
  runId: string;
  datasetDate: string;
  symbol: string;
  strategy: string;
  executionModel: string;
  eventCount: number;
  orderCount: number;
  fillCount: number;
  status: string;
  runDirectory: string;
};

export type BookLevel = {
  price: string;
  qty: string;
  cumulativeQty: string;
};

export type Snapshot = {
  runId: string;
  symbol: string;
  datasetDate: string;
  strategy: string;
  executionModel: string;
  delayUs: number;
  feeBps: number;
  replayTime: string;
  eventCursor: string;
  state: string;
  progress: number;
  mid: string;
  bid: string;
  ask: string;
  spread: string;
  microprice: string;
  signal: string;
  chart: string;
  book: string;
  eventTape: string;
  orders: string;
  fills: string;
  positionText: string;
  pnlText: string;
  causal: string;
  warning: string;
  rawEvent: string;
  selectedFill: string;
  cursor: number;
  replayState: string;
  quote: {
    bid: string;
    ask: string;
    mid: string;
    spread: string;
    microprice: string;
    bidQty: string;
    askQty: string;
  };
  orderBook: {
    bestBid: string;
    bestAsk: string;
    spread: string;
    bids: BookLevel[];
    asks: BookLevel[];
    updateCount: number;
    snapshotBatchCount: number;
    quality: string;
  };
  strategySignal: {
    profile: string;
    signal: string;
    threshold: string;
    reason: string;
    observedQuote: string;
    observedTsUs: string;
  };
  orderIntent: {
    intentId: string;
    clientOrderId: string;
    side: string;
    qty: string;
    reason: string;
    observedQuote: string;
    observedTsUs: string;
  };
  orderArrival: {
    orderId: string;
    arrivalQuote: string;
    arrivalTsUs: string;
    actualLatencyUs: string;
    latencySlippageBps: string;
    orderStatus: string;
  };
  fill: {
    fillId: string;
    orderId: string;
    side: string;
    price: string;
    qty: string;
    fee: string;
    liquidity: string;
    realizedPnlDelta: string;
    netPnlDelta: string;
    attribution: string;
  };
  position: {
    positionQty: string;
    avgEntryPrice: string;
    equity: string;
    feesPaid: string;
  };
  pnl: {
    realizedPnl: string;
    unrealizedPnl: string;
    selectedFillDelta: string;
    netEquity: string;
  };
  pnlCurve: Array<{
    eventPos: number;
    timestamp: string;
    realizedPnl: number;
    unrealizedPnl: number;
    netPnl: number;
  }>;
  l2Quality: {
    status: string;
    warning: string;
  };
};

export type RunConfig = {
  date: string;
  profile: string;
  fillModel: string;
  latencyUs: number;
  feeBps: number;
  startingCash: number;
};

export type StageData = { eventId: string; eventPos: number; timestamp: string; data: Record<string, any> } | null;
export type CausalChain = { signal: StageData; intent: StageData; arrival: StageData; fill: StageData; account: StageData; missing: string[] };
export type ReplayStateV2 = {
  schemaVersion: 2; sessionId: string; version: number; runId: string; symbol: string;
  datasetDate: string | null; strategy: string | null; executionModel: string | null;
  delayUs: number | null; feeBps: number | null; cursor: number; eventCount: number;
  eventId: string; eventType: string; timestamp: string; clockTimestamp: string;
  startTimestamp: string; endTimestamp: string; timestampRegressions: number;
  playing: boolean; speed: number; selectedFillEventId: string | null;
  quote: {bid: number | null; ask: number | null; mid: number | null; spreadBps: number | null; microprice: number | null; bidQty: number | null; askQty: number | null} | null;
  account: Record<string, number | null> | null; chain: CausalChain;
  orderBook: {bids: Array<{price: number; qty: number; cumulative_qty: number}>; asks: Array<{price: number; qty: number; cumulative_qty: number}>; updateCount: number; snapshotBatchCount: number; quality: {status: string; warnings?: string[]}};
};
export type PricePoint = {eventPos: number; timestamp: string; clockTimestamp: string; bid: number | null; ask: number | null; mid: number | null};
export type ReplayWindow = {sessionId: string; version: number; cursorUpper: number; prices: PricePoint[]; pnl: Array<{eventPos: number; timestamp: string; clockTimestamp: string; realizedPnl: number | null; unrealizedPnl: number | null; netPnl: number | null}>; markers: Array<{eventId: string; eventPos: number; timestamp: string; clockTimestamp: string; eventType: string; mid: number | null}>; markerCount: number};
export type ReplayRow = {eventId: string; eventPos: number; eventType: string; timestamp: string; source: string; intentId: string | null; orderId: string | null; fillId: string | null; side: string | null; qty: number | null; price: number | null; fee: number | null; status: string | null};
export type ReplayRows = {sessionId: string; version: number; cursorUpper: number; rows: ReplayRow[]; total: number; offset: number; limit: number};
export type ReplayInspection = {sessionId: string; version: number; rawEvent: Record<string, unknown>; chain: CausalChain};
