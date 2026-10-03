import { useEffect, useRef, useState } from "react";
import type { ReplayStateV2, ReplayWindow, ReplayRows, ReplayInspection } from "./types";
import { getReplayWindow, queryReplayRows, inspectReplayEvent } from "./lib/bridge";
import { fmt } from "./lib/presentation";

export function useReplayWindow(state: ReplayStateV2, range: string) {
  const [result, setResult] = useState<ReplayWindow | null>(null);
  const [error, setError] = useState("");
  const latest = useRef({state,range}); latest.current={state,range};
  const busy = useRef(false);
  useEffect(() => {
    let cancelled=false;
    const poll=async()=>{
      if(busy.current)return;
      const {state:s,range:r}=latest.current;busy.current=true;
      try {
        const stop=BigInt(s.clockTimestamp),span=BigInt(r === "10" ? 10_000_000 : 60_000_000);
        const start=r === "all" ? null : (stop>span ? stop-span : 0n).toString();
        const value=await getReplayWindow(s,start,s.clockTimestamp);
        const now=latest.current.state;
        if(!cancelled && value.sessionId===now.sessionId && value.cursorUpper===now.cursor) {setResult(value);setError("");}
      } catch(e) {if(!cancelled)setError(String(e));}
      finally {busy.current=false;}
    };
    void poll();const timer=window.setInterval(()=>void poll(),120);
    return()=>{cancelled=true;window.clearInterval(timer);};
  }, [state.sessionId,range,state.playing]);
  const visible=result?.sessionId===state.sessionId && result.cursorUpper===state.cursor ? result : null;
  return {data:visible,error};
}
type WindowResult = ReturnType<typeof useReplayWindow>;
const time = (us: string) => new Date(Number(BigInt(us)/1000n)).toISOString().slice(11,23);
// Subtract as integers before conversion to preserve microsecond spacing.
function xTime(timestamp: string, start: string, stop: string) {
  const span = BigInt(stop)-BigInt(start);
  return span > 0n ? Number(BigInt(timestamp)-BigInt(start))/Number(span)*100 : 50;
}
export function PriceChart({state, window, range, onRange, onInspect}: {state: ReplayStateV2; window: WindowResult; range: string; onRange: (v:string)=>void; onInspect:(id:string,kind:string)=>void}) {
  const [hover, setHover] = useState<number | null>(null);
  const data = window.data;
  const prices = data?.prices.filter(p=>p.mid !== null) ?? [];
  const markers = data?.markers ?? [];
  const start = prices[0]?.clockTimestamp ?? state.clockTimestamp;
  const stop = prices.at(-1)?.clockTimestamp ?? state.clockTimestamp;
  const plotted = [...prices.map(p=>p.mid!).filter(Number.isFinite), ...markers.map(m=>m.price ?? m.mid).filter((v): v is number=>v !== null && Number.isFinite(v))];
  const min = plotted.length ? Math.min(...plotted) : 0;
  const max = plotted.length ? Math.max(...plotted) : 0;
  const span = max-min || Math.max(Math.abs(max)*0.0001,1e-8);
  const y = (p:number) => 125-(p-min)/span*110;
  const points = prices.map(p=>`${xTime(p.clockTimestamp,start,stop)},${y(p.mid!)}`).join(" ");
  const nearest = hover === null ? null : prices.reduce<typeof prices[number] | null>((best,p)=>!best || Math.abs(xTime(p.clockTimestamp,start,stop)-hover)<Math.abs(xTime(best.clockTimestamp,start,stop)-hover) ? p : best,null);
  return <section className="chart-panel panel"><div className="panel-heading"><div><h2>Historical price & execution</h2><p>Mid price with strategy, order and actual fill markers</p></div><select aria-label="Price time window" value={range} onChange={e=>onRange(e.target.value)}><option value="all">All visible</option><option value="60">Last 60s</option><option value="10">Last 10s</option></select></div><div className="chart-wrap" onMouseMove={e=>{const r=e.currentTarget.getBoundingClientRect();setHover((e.clientX-r.left)/r.width*100);}} onMouseLeave={()=>setHover(null)}><svg viewBox="0 0 100 140" preserveAspectRatio="none" role="img" aria-label="Historical price with strategy and execution markers"><polyline points={points} fill="none" stroke="#58d2b2" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />{markers.filter(m=>(m.price ?? m.mid)!==null).map(m=>{const markerPrice=m.price ?? m.mid!;const isFill=m.eventType === "fill_created" || m.eventType === "fill";const fillTone=m.side === "sell" ? "#ef7f7f" : "#58d2b2";return <circle key={m.eventId} cx={xTime(m.clockTimestamp,start,stop)} cy={y(markerPrice)} r={isFill ? 1.9 : 0.75} fill={isFill ? fillTone : m.eventType === "order_arrival" ? "#b796e9" : m.eventType === "order_intent" ? "#80b9ef" : "#f1b85b"} className="event-marker" onClick={()=>onInspect(m.eventId,m.eventType)}><title>{[m.side?.toUpperCase(),m.eventType,time(m.timestamp),`price ${fmt(markerPrice,8)}`,m.signal==null?null:`signal ${fmt(m.signal,3)}`,`event ${m.eventId}`].filter(Boolean).join(" · ")}</title></circle>})}</svg><div className="chart-readout"><span>{nearest ? time(nearest.timestamp) : "mid"}</span><strong>{fmt(nearest?.mid ?? state.quote?.mid,8)}</strong><span>{nearest ? `bid ${fmt(nearest.bid,8)} · ask ${fmt(nearest.ask,8)}` : window.error || (!data ? "Loading window…" : `${prices.length} price points · ${markers.length} markers`)}</span></div></div><div className="chart-axis"><span>{time(start)}</span><span>{fmt(min,8)} – {fmt(max,8)}</span><span>{time(stop)}</span></div><div className="chart-legend"><span><i className="legend-dot quote" /> signal</span><span><i className="legend-dot intent" /> intent</span><span><i className="legend-dot arrival" /> arrival</span><span><i className="legend-dot fill" /> buy fill</span><span><i className="legend-dot sell-fill" /> sell fill</span></div>{data && data.markerCount > data.markers.length && <small>{data.markers.length} of {data.markerCount} markers; use a shorter window for detail.</small>}</section>;
}
export function EquityChart({window}: {window:WindowResult}) {
  const values=window.data?.pnl ?? [];
  const known=values.filter(v=>v.netPnl!==null);
  const min=Math.min(...known.map(p=>p.netPnl!),0),max=Math.max(...known.map(p=>p.netPnl!),0);
  const y=(p:number)=>128-(p-min)/(max-min || 1)*112;
  const start=values[0]?.clockTimestamp ?? "0",stop=values.at(-1)?.clockTimestamp ?? "0";
  // Missing account/mark creates a gap, never a fabricated zero.
  const segments:string[]=[];let current:string[]=[];
  for (const p of values) {if(p.netPnl===null){if(current.length)segments.push(current.join(" "));current=[];}else current.push(`${xTime(p.clockTimestamp,start,stop)},${y(p.netPnl)}`);}
  if(current.length)segments.push(current.join(" "));
  return <section className="pnl-chart panel"><div className="panel-heading"><div><h2>P&amp;L path</h2><p>Runner ledger · current quote valuation</p></div></div><div className="pnl-chart-wrap"><svg viewBox="0 0 100 140" preserveAspectRatio="none" role="img" aria-label="Account PnL in event time"><line x1="0" x2="100" y1={y(0)} y2={y(0)} stroke="#33454b" strokeDasharray="2 2" />{segments.map((points,i)=><polyline key={i} points={points} fill="none" stroke="#f1b85b" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />)}</svg><div className="pnl-axis"><span>{fmt(max,4)}</span><span>{fmt(min,4)}</span></div></div><div className="pnl-footer"><span>net PnL</span><strong>{fmt(values.at(-1)?.netPnl)}</strong><small>{known.length ? `${known.length} ledger / quote points` : window.error || "Account unavailable"}</small></div></section>;
}
export function ReplayTable({state,kind,onInspect}:{state:ReplayStateV2;kind:string|null;onInspect:(id:string,kind:string)=>void}) {
  const [offset,setOffset]=useState(0);const [result,setResult]=useState<ReplayRows|null>(null);const [error,setError]=useState("");
  useEffect(()=>setOffset(0),[kind,state.sessionId]);
  const latest=useRef({state,kind,offset});latest.current={state,kind,offset};const busy=useRef(false);
  useEffect(()=>{let cancelled=false;const poll=async()=>{if(busy.current)return;const request=latest.current;busy.current=true;try{const r=await queryReplayRows(request.state,request.kind,request.offset);const now=latest.current;if(!cancelled && r.sessionId===now.state.sessionId && r.cursorUpper===now.state.cursor && r.offset===now.offset){setResult(r);setError("");}}catch(e){if(!cancelled)setError(String(e));}finally{busy.current=false;}};void poll();const timer=window.setInterval(()=>void poll(),120);return()=>{cancelled=true;window.clearInterval(timer);};},[state.sessionId,kind,offset,state.playing]);
  const rows=result?.sessionId===state.sessionId && result.cursorUpper===state.cursor && result.offset===offset ? result.rows : [];
  return <div className="replay-rows"><table><thead><tr><th>Event</th><th>Time (UTC)</th><th>Type / ID</th><th>Side</th><th>Qty</th><th>Price</th><th>Fee</th><th>Status</th></tr></thead><tbody>{rows.map(r=><tr key={r.eventId} className={state.selectedFillEventId===r.eventId ? "selected" : ""}><td><button onClick={()=>onInspect(r.eventId,r.eventType)}>#{r.eventId}</button></td><td title={r.timestamp}>{time(r.timestamp)}</td><td>{r.eventType} {r.fillId ?? r.intentId ?? ""}</td><td>{r.side ?? "—"}</td><td>{fmt(r.qty,3)}</td><td>{fmt(r.price,8)}</td><td>{fmt(r.fee,8)}</td><td>{r.status ?? "—"}</td></tr>)}</tbody></table>{error && <p role="alert">{error}</p>}<div className="row-pagination"><button disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-30))}>Previous</button><span>{offset+1}–{offset+rows.length} / {result?.total ?? 0}</span><button disabled={!result || offset+30>=result.total} onClick={()=>setOffset(offset+30)}>Next</button></div></div>;
}
export function RawInspector({state,eventId}:{state:ReplayStateV2;eventId:string|null}) {
  const [result,setResult]=useState<ReplayInspection|null>(null);const [error,setError]=useState("");
  const current=useRef(state);current.current=state;
  useEffect(()=>{setResult(null);setError("");if(!eventId)return;let cancelled=false;const s=current.current;inspectReplayEvent(s,eventId).then(r=>{if(!cancelled)setResult(r);}).catch(e=>{if(!cancelled)setError(String(e));});return()=>{cancelled=true;};},[eventId,state.sessionId]);
  const raw=result?.sessionId===state.sessionId ? JSON.stringify(result.rawEvent,null,2) : "Select an event row or chart marker to read its JSON.";
  return <section className="raw-event panel"><div className="panel-kicker"><span>RAW EVENT JSON · {eventId ?? "—"}</span><button className="copy-button" disabled={!result} onClick={()=>void navigator.clipboard?.writeText(raw)}>Copy raw JSON</button></div><pre>{error || raw}</pre></section>;
}

export function HistoricalTradeAnalysis({state,onInspect}:{state:ReplayStateV2;onInspect:(id:string,kind:string)=>void}) {
  const [rows,setRows]=useState<ReplayRows["rows"]>([]);
  const [total,setTotal]=useState(0);
  const [error,setError]=useState("");
  const latest=useRef(state);latest.current=state;
  const busy=useRef(false);
  useEffect(()=>{let cancelled=false;const poll=async()=>{if(busy.current)return;const request=latest.current;busy.current=true;try{
    const [created,plain]=await Promise.all([
      queryReplayRows(request,"fill_created",0,100),
      queryReplayRows(request,"fill",0,100)
    ]);
    const now=latest.current;
    if(cancelled || created.sessionId!==now.sessionId || plain.sessionId!==now.sessionId || created.cursorUpper!==now.cursor || plain.cursorUpper!==now.cursor)return;
    const unique=new Map<string,ReplayRows["rows"][number]>();
    for(const row of [...created.rows,...plain.rows]) unique.set(row.fillId ? `fill:${row.fillId}` : `event:${row.eventId}`,row);
    setRows([...unique.values()].sort((a,b)=>b.eventPos-a.eventPos));
    setTotal(Math.max(created.total,plain.total,unique.size));
    setError("");
  }catch(e){if(!cancelled)setError(String(e));}finally{busy.current=false;}};void poll();const timer=window.setInterval(()=>void poll(),250);return()=>{cancelled=true;window.clearInterval(timer);};},[state.sessionId,state.playing]);

  const realized=rows.filter(r=>r.realizedPnlDelta!==null).reduce((sum,r)=>sum+(r.realizedPnlDelta ?? 0),0);
  const execution=rows.filter(r=>r.netPnlDelta!==null).reduce((sum,r)=>sum+(r.netPnlDelta ?? 0),0);
  const slips=rows.map(r=>r.latencySlippageBps).filter((v):v is number=>v!==null && Number.isFinite(v));
  const avgSlip=slips.length ? slips.reduce((a,b)=>a+b,0)/slips.length : null;
  const completed=rows.filter(r=>Math.abs(r.realizedPnlDelta ?? 0)>1e-12).length;
  return <section className="historical-trades panel">
    <div className="panel-heading"><div><h2>Historical trades</h2><p>Runner-recorded fills up to the current replay cursor</p></div><span className="history-count">{total} fills</span></div>
    <div className="history-metrics">
      <div><span>REALIZED Δ</span><strong className={realized>=0?"positive-text":"negative-text"}>{fmt(realized,4)}</strong></div>
      <div><span>EXECUTION Δ</span><strong className={execution>=0?"positive-text":"negative-text"}>{fmt(execution,4)}</strong></div>
      <div><span>AVG LATENCY SLIP</span><strong>{avgSlip===null?"—":`${fmt(avgSlip,3)} bps`}</strong></div>
      <div><span>REALIZING FILLS</span><strong>{completed}</strong></div>
    </div>
    <div className="history-table-wrap"><table className="history-table"><thead><tr><th>Time</th><th>Side</th><th>Qty</th><th>Fill</th><th>Signal</th><th>Latency slip</th><th>Realized Δ</th><th>Exec Δ</th></tr></thead><tbody>
      {rows.slice(0,10).map(r=><tr key={r.eventId} onClick={()=>onInspect(r.eventId,r.eventType)}><td>{time(r.timestamp)}</td><td className={r.side==="buy"?"positive-text":r.side==="sell"?"negative-text":""}>{r.side?.toUpperCase() ?? "—"}</td><td>{fmt(r.qty,3)}</td><td>{fmt(r.price,8)}</td><td title={r.reason ?? ""}>{fmt(r.signal,3)}</td><td>{r.latencySlippageBps===null?"—":`${fmt(r.latencySlippageBps,3)} bps`}</td><td className={(r.realizedPnlDelta ?? 0)>=0?"positive-text":"negative-text"}>{fmt(r.realizedPnlDelta,4)}</td><td className={(r.netPnlDelta ?? 0)>=0?"positive-text":"negative-text"}>{fmt(r.netPnlDelta,4)}</td></tr>)}
      {!rows.length && <tr><td colSpan={8}>{error || "No fills have occurred at this replay cursor."}</td></tr>}
    </tbody></table></div>
    <p className="history-note">Realized Δ is the realized-account change recorded at that fill; execution Δ is the immediate equity change at execution. Neither is fabricated by the UI.</p>
  </section>;
}
