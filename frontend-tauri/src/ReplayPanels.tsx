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
  const start = prices[0]?.clockTimestamp ?? state.clockTimestamp;
  const stop = prices.at(-1)?.clockTimestamp ?? state.clockTimestamp;
  const min = prices.length ? Math.min(...prices.map(p=>p.mid!)) : 0;
  const max = prices.length ? Math.max(...prices.map(p=>p.mid!)) : 0;
  const span = max-min || Math.max(Math.abs(max)*0.0001,1e-8);
  const y = (p:number) => 125-(p-min)/span*110;
  const points = prices.map(p=>`${xTime(p.clockTimestamp,start,stop)},${y(p.mid!)}`).join(" ");
  const nearest = hover === null ? null : prices.reduce<typeof prices[number] | null>((best,p)=>!best || Math.abs(xTime(p.clockTimestamp,start,stop)-hover)<Math.abs(xTime(best.clockTimestamp,start,stop)-hover) ? p : best,null);
  return <section className="chart-panel panel"><div className="panel-heading"><div><h2>Price path</h2><p>Mid price · event time</p></div><select aria-label="Price time window" value={range} onChange={e=>onRange(e.target.value)}><option value="all">All visible</option><option value="60">Last 60s</option><option value="10">Last 10s</option></select></div><div className="chart-wrap" onMouseMove={e=>{const r=e.currentTarget.getBoundingClientRect();setHover((e.clientX-r.left)/r.width*100);}} onMouseLeave={()=>setHover(null)}><svg viewBox="0 0 100 140" preserveAspectRatio="none" role="img" aria-label="Mid price in event time"><polyline points={points} fill="none" stroke="#58d2b2" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />{data?.markers.filter(m=>m.mid!==null).map(m=><circle key={m.eventId} cx={xTime(m.clockTimestamp,start,stop)} cy={y(m.mid!)} r={m.eventType === "fill_created" || m.eventType === "fill" ? 1.7 : 0.7} fill={m.eventType.includes("fill") ? "#58d2b2" : m.eventType === "order_arrival" ? "#b796e9" : m.eventType === "order_intent" ? "#80b9ef" : "#f1b85b"} className="event-marker" onClick={()=>onInspect(m.eventId,m.eventType)}><title>{m.eventType} · {time(m.timestamp)} · event {m.eventId}</title></circle>)}</svg><div className="chart-readout"><span>{nearest ? time(nearest.timestamp) : "mid"}</span><strong>{fmt(nearest?.mid ?? state.quote?.mid,8)}</strong><span>{nearest ? `bid ${fmt(nearest.bid,8)} · ask ${fmt(nearest.ask,8)}` : window.error || (!data ? "Loading window…" : `${prices.length} points`)}</span></div></div><div className="chart-axis"><span>{time(start)}</span><span>{fmt(min,8)} – {fmt(max,8)}</span><span>{time(stop)}</span></div><div className="chart-legend"><span><i className="legend-dot quote" /> quote / signal</span><span><i className="legend-dot intent" /> intent</span><span><i className="legend-dot arrival" /> arrival</span><span><i className="legend-dot fill" /> fill</span></div>{data && data.markerCount > data.markers.length && <small>{data.markers.length} of {data.markerCount} markers; use a shorter window for detail.</small>}</section>;
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
