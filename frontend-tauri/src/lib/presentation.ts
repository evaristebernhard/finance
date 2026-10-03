import type { ReplayStateV2, Snapshot } from "../types";
export const fmt = (v: unknown, digits = 6): string => typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : typeof v === "string" ? v : "—";
const id = (v: unknown) => v == null ? "—" : String(v);
const quoteText = (v: any) => v ? `bid ${fmt(v.bid,8)} / ask ${fmt(v.ask,8)}` : "—";
// Formatting is entirely a presentation concern; the bridge transports numbers/null.
export function present(s: ReplayStateV2): Snapshot {
  const q = s.quote;
  const chain = s.chain;
  const sig = chain.signal?.data;
  const intent = chain.intent?.data;
  const order = intent?.intent?.order ?? intent?.order;
  const arrival = chain.arrival?.data;
  const fillData = chain.fill?.data;
  const fill = fillData?.fill;
  const a = s.account;
  const status = s.playing ? "REPLAYING" : s.cursor + 1 === s.eventCount ? "RUN COMPLETE" : "PAUSED";
  const quality = s.orderBook.quality;
  const warning = quality.warnings?.join(" · ") || (s.orderBook.snapshotBatchCount ? "L2 snapshots · incremental semantics unverified" : quality.status);
  const stageQuote = (v: any) => quoteText(v?.observed_quote ?? v?.intent?.observed_quote);
  return {
    runId:s.runId, symbol:s.symbol ?? "—", datasetDate:s.datasetDate ?? "—",strategy:typeof s.strategy === "string" ? s.strategy : "—", executionModel:s.executionModel ?? "—",delayUs:s.delayUs ?? 0,feeBps:s.feeBps ?? 0,
    replayTime:s.timestamp,eventCursor:`${s.cursor+1} / ${s.eventCount}`,state:s.eventType,progress:s.eventCount>1 ? s.cursor/(s.eventCount-1)*100 : 100,
    cursor:s.cursor,replayState:status,mid:fmt(q?.mid,8),bid:fmt(q?.bid,8),ask:fmt(q?.ask,8),spread:q?.spreadBps == null ? "—" : `${fmt(q.spreadBps,2)} bps`,microprice:fmt(q?.microprice,8),signal:fmt(sig?.signal,3),chart:"",book:"",eventTape:"",orders:"",fills:"",positionText:JSON.stringify(a,null,2),pnlText:"",causal:JSON.stringify(chain,null,2),rawEvent:"",selectedFill:chain.fill?.eventId ?? "—",warning,
    quote:{bid:fmt(q?.bid,8),ask:fmt(q?.ask,8),mid:fmt(q?.mid,8),spread:fmt(q?.spreadBps,2),microprice:fmt(q?.microprice,8),bidQty:fmt(q?.bidQty,3),askQty:fmt(q?.askQty,3)},
    orderBook:{bestBid:fmt(s.orderBook.bids[0]?.price ?? q?.bid,8),bestAsk:fmt(s.orderBook.asks[0]?.price ?? q?.ask,8),spread:fmt(q?.spreadBps,2),bids:s.orderBook.bids.map(l=>({price:fmt(l.price,8),qty:fmt(l.qty,3),cumulativeQty:fmt(l.cumulative_qty,3)})),asks:s.orderBook.asks.map(l=>({price:fmt(l.price,8),qty:fmt(l.qty,3),cumulativeQty:fmt(l.cumulative_qty,3)})),updateCount:s.orderBook.updateCount,snapshotBatchCount:s.orderBook.snapshotBatchCount,quality:quality.status},
    strategySignal:{profile:id(sig?.strategy_profile ?? (chain.signal ? s.strategy : null)),signal:fmt(sig?.signal,3),threshold:fmt(sig?.threshold,3),reason:id(sig?.reason),observedQuote:stageQuote(sig),observedTsUs:id(sig?.observed_ts_us)},
    orderIntent:{intentId:id(intent?.intent_id ?? intent?.intent?.intent_id),clientOrderId:id(intent?.client_order_id ?? order?.client_order_id),side:id(order?.side),qty:fmt(order?.qty,3),reason:id(intent?.reason ?? intent?.intent?.reason),observedQuote:stageQuote(intent),observedTsUs:id(intent?.observed_ts_us)},
    orderArrival:{orderId:id(arrival?.order_id ?? arrival?.order?.id),arrivalQuote:quoteText(arrival?.arrival_quote),arrivalTsUs:id(arrival?.arrival_ts_us),actualLatencyUs:arrival?.actual_latency_us == null ? "—" : `${fmt(arrival.actual_latency_us,0)} µs`,latencySlippageBps:fmt(arrival?.latency_slippage_bps,3),orderStatus:id(arrival?.order_status ?? arrival?.order?.status)},
    fill:{fillId:id(fillData?.fill_id ?? fill?.id),orderId:id(fillData?.order_id ?? fill?.order_id),side:id(fill?.side),price:fmt(fill?.price,8),qty:fmt(fill?.qty,3),fee:fmt(fillData?.fee ?? fill?.fee,8),liquidity:id(fill?.liquidity),realizedPnlDelta:fmt(fillData?.realized_pnl_delta),netPnlDelta:fmt(fillData?.net_pnl_delta),attribution:fillData?.attribution ? Object.entries(fillData.attribution).map(([k,v])=>`${k}: ${fmt(v)}`).join(" · ") : "—"},
    position:{positionQty:fmt(a?.position_qty,3),avgEntryPrice:fmt(a?.avg_entry_price,8),equity:fmt(a?.equity),feesPaid:fmt(a?.fees_paid,8)},pnl:{realizedPnl:fmt(a?.realized_pnl),unrealizedPnl:fmt(a?.unrealized_pnl),selectedFillDelta:fmt(fillData?.net_pnl_delta),netEquity:fmt(a?.equity)},pnlCurve:[],l2Quality:{status:quality.status,warning}
  };
}
