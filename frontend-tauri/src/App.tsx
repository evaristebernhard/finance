import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowUpFromLine,
  BarChart3,
  BookOpen,
  ChevronRight,
  CirclePause,
  CirclePlay,
  Database,
  Gauge,
  Library,
  ListTree,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Search,
  Settings2,
  StepBack,
  StepForward,
  Target,
  TimerReset,
  WalletCards,
  Zap,
} from "lucide-react";
import {
  listRuns,
  openRun,
  replayCommand,
  seek,
  selectFill,
  watchReplay,
  inTauri,
  startRun,
} from "./lib/bridge";
import type { RunConfig, RunEntry, Snapshot, ReplayStateV2 } from "./types";
import "./styles.css";
import { present } from "./lib/presentation";
import { PriceChart, EquityChart, HistoricalTradeAnalysis, ReplayTable, RawInspector, useReplayWindow } from "./ReplayPanels";

type Page = "library" | "setup" | "workbench";
type Tab = "Events" | "Signals" | "Orders" | "Fills" | "Position" | "PnL";

const tabs: Tab[] = ["Events", "Signals", "Orders", "Fills", "Position", "PnL"];

export default function App() {
  const [page, setPage] = useState<Page>("library");
  const [runs, setRuns] = useState<RunEntry[]>([]);
  const [replay, setReplay] = useState<ReplayStateV2 | null>(null);
  const snapshot = useMemo(() => replay ? present(replay) : null, [replay]);
  const latest = useRef<ReplayStateV2 | null>(null);
  const opening = useRef(0);
  const switching = useRef(false);
  function accept(next: ReplayStateV2) {
    if (switching.current) return;
    const current = latest.current;
    if (current && (BigInt(next.sessionId) < BigInt(current.sessionId) || (next.sessionId === current.sessionId && next.version <= current.version))) return;
    latest.current = next;
    setReplay(next);
  }
  useEffect(() => {
    if (!inTauri()) { setNotice("Open the Tauri desktop app to read local Runner artifacts."); return; }
    let cancelled = false;
    let unlisten: (() => void) | undefined;
    watchReplay(accept).then(stop => { if (cancelled) stop(); else unlisten = stop; }).catch(e => setNotice(String(e)));
    return () => { cancelled = true; unlisten?.(); };
  }, []);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("Local Runner workspace ready");
  const [config, setConfig] = useState<RunConfig>({
    date: "2026-10-01",
    profile: "tfi",
    fillModel: "top-of-book",
    latencyUs: 50000,
    feeBps: 0,
    startingCash: 10000,
  });

  useEffect(() => {
    void refreshRuns();
  }, []);

  async function refreshRuns() {
    try {
      setRuns(await listRuns());
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not load Run Library");
    }
  }

  async function loadRun(runId: string) {
    const request = ++opening.current;
    switching.current = true;
    setLoading(true);
    setNotice(`Loading ${runId} from Runner artifacts…`);
    try {
      const next = await openRun(runId);
      if (request !== opening.current) return;
      switching.current = false;
      accept(next);
      setPage("workbench");
      setNotice("Runner artifacts loaded · replay is ready");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not open run");
    } finally {
      if (request === opening.current) { switching.current = false; setLoading(false); }
    }
  }

  async function command(action: string) {
    try {
      accept(await replayCommand(action));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Replay command failed");
    }
  }

  async function moveCursor(value: number) {
    try {
      accept(await seek(value));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Seek failed");
    }
  }

  async function createRun() {
    setLoading(true);
    setPage("workbench");
    setNotice("Runner is generating a new event-level artifact…");
    try {
      accept(await startRun(config));
      await refreshRuns();
      setNotice("Run complete · inspect the replay story below");
    } catch (error) {
      setPage("setup");
      setNotice(error instanceof Error ? error.message : "Runner failed");
    } finally {
      setLoading(false);
    }
  }

  async function inspectFill(fillEventId: string) {
    try { accept(await selectFill(fillEventId)); }
    catch (error) { setNotice(String(error)); }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">Q</div>
          <div>
            <strong>Quant Replay Studio</strong>
            <span>Historical replay & strategy analysis</span>
          </div>
        </div>
        <div className="sidebar-rule" />
        <nav className="nav-stack" aria-label="Primary">
          <NavItem icon={<Library size={16} />} label="Experiments" note="runs · replay stories" active={page === "library"} onClick={() => setPage("library")} />
          <NavItem icon={<Settings2 size={16} />} label="New Experiment" note="data · strategy · execution" active={page === "setup"} onClick={() => setPage("setup")} />
          <NavItem icon={<Activity size={16} />} label="Replay Analysis" note="market · trades · PnL" active={page === "workbench"} disabled={!snapshot} onClick={() => snapshot && setPage("workbench")} />
        </nav>
        <div className="sidebar-spacer" />
        <div className="status-block">
          <span className="eyebrow">WORKSPACE STATUS</span>
          <p>{notice}</p>
        </div>
        <div className="selected-run">
          <span className="eyebrow">SELECTED RUN</span>
          <code>{snapshot?.runId ?? "—"}</code>
        </div>
      </aside>

      <main className="main-content">
        {page === "library" && <RunLibrary runs={runs} onOpen={loadRun} onCreate={() => setPage("setup")} />}
        {page === "setup" && <SetupPage config={config} setConfig={setConfig} onCreate={createRun} loading={loading} />}
        {page === "workbench" && snapshot && replay && (
          <Workbench
            key={replay.sessionId}
            replay={replay}
            snapshot={snapshot}
            loading={loading}
            onLibrary={() => setPage("library")}
            onCommand={command}
            onSeek={moveCursor}
            onInspectFill={inspectFill}
          />
        )}
        {page === "workbench" && !snapshot && <EmptyWorkbench onLibrary={() => setPage("library")} />}
      </main>
    </div>
  );
}

function NavItem({ icon, label, note, active, disabled, onClick }: { icon: React.ReactNode; label: string; note: string; active: boolean; disabled?: boolean; onClick: () => void }) {
  return (
    <button className={`nav-item ${active ? "active" : ""}`} disabled={disabled} onClick={onClick}>
      <span className="nav-icon">{icon}</span>
      <span className="nav-copy"><strong>{label}</strong><small>{note}</small></span>
      {active && <ChevronRight size={14} className="nav-chevron" />}
    </button>
  );
}

function PageHeader({ kicker, title, description, action }: { kicker: string; title: string; description: string; action?: React.ReactNode }) {
  return <div className="page-header"><div><span className="eyebrow">{kicker}</span><h1>{title}</h1><p>{description}</p></div>{action}</div>;
}

function RunLibrary({ runs, onOpen, onCreate }: { runs: RunEntry[]; onOpen: (runId: string) => void; onCreate: () => void }) {
  return (
    <div className="page-stack">
      <PageHeader kicker="HISTORICAL STRATEGY REPLAY & ANALYSIS" title="Replay the market. See the trades. Study the outcome." description="Open a completed strategy run as a historical market session: follow price and order flow, see where the strategy acted, inspect actual fills, and connect those decisions to position and PnL." action={<PrimaryButton icon={<Plus size={15} />} onClick={onCreate}>New experiment</PrimaryButton>} />
      <section className="product-thesis" aria-label="Product workflow">
        <div className="thesis-card"><span>01 · MARKET REPLAY</span><strong>Watch the historical market unfold</strong><p>Price, book state, strategy signals, orders and fills share one event-time cursor so the session can be studied as it happened.</p></div>
        <div className="thesis-card"><span>02 · TRADE REVIEW</span><strong>See where the strategy entered and what happened</strong><p>Actual Runner fills, latency slippage and realized/execution PnL stay next to the price path instead of disappearing into raw logs.</p></div>
        <div className="thesis-card"><span>03 · CONTEXT</span><strong>Study the conditions around useful and poor trades</strong><p>Signal strength, threshold, spread, order-book state and execution details provide context for historical research without inventing new fills in the UI.</p></div>
      </section>
      <div className="library-toolbar"><div className="library-count"><Database size={15} /> <strong>{runs.length}</strong> experiments available</div><div className="library-root"><span>ARTIFACT ROOT</span><code>systems/quant_replay_engine/runs</code></div></div>
      <section className="run-table panel">
        <div className="table-head"><span>RUN</span><span>DATASET</span><span>STRATEGY</span><span>EXECUTION</span><span>EVENTS</span><span>ORDERS</span><span>FILLS</span><span>STATUS</span><span /></div>
        {runs.length === 0 && <div className="empty-row">No experiments yet. Create one to produce a deterministic replay artifact.</div>}
        {runs.map((run) => <button className="run-row" key={run.runId} onClick={() => onOpen(run.runId)}><span className="run-name"><strong>{run.runId}</strong><small>{run.symbol}</small></span><span>{run.datasetDate}</span><span className="accent-text">{run.strategy}</span><span>{run.executionModel}</span><span>{run.eventCount.toLocaleString()}</span><span>{run.orderCount}</span><span>{run.fillCount}</span><Status status={run.status} /><span className="row-action">Open <ChevronRight size={14} /></span></button>)}
      </section>
      <div className="library-foot"><div className="foot-icon"><ListTree size={17} /></div><div><strong>Read-only artifact boundary</strong><p>Run Library reads manifest.json and summary.json only. Opening a run builds read-only event offsets and state indexes.</p></div><span className="story-route">Signal <ChevronRight size={13} /> Order <ChevronRight size={13} /> Arrival <ChevronRight size={13} /> Fill <ChevronRight size={13} /> PnL</span></div>
    </div>
  );
}

function SetupPage({ config, setConfig, onCreate, loading }: { config: RunConfig; setConfig: React.Dispatch<React.SetStateAction<RunConfig>>; onCreate: () => void; loading: boolean }) {
  return (
    <div className="page-stack">
      <PageHeader kicker="NEW HISTORICAL RUN" title="Choose what you want to replay and study" description="Select the dataset, strategy and execution assumptions. The Runner produces the fills and account history; Replay Analysis then shows the market, trades and PnL without re-simulating them in the UI." />
      <div className="setup-grid">
        <section className="setup-card panel"><PanelHeading icon={<Database size={16} />} title="Dataset" subtitle="Canonical CCUSDT market truth" /><div className="dataset-preview"><div className="dataset-status"><span className="status-dot ready" />AVAILABLE</div><strong>CCUSDT / 2026-10-01</strong><small>quote · trade · optional L2 batches</small></div><div className="setup-lines"><span><b>MAX EVENTS</b><strong>25,000</strong></span><span><b>ARTIFACTS</b><strong>manifest · summary · events · index</strong></span><span><b>DATA BOUNDARY</b><strong>Runner-owned values only</strong></span></div></section>
        <section className="setup-card panel"><PanelHeading icon={<Target size={16} />} title="Strategy + execution" subtitle="Make every execution assumption explicit and reproducible" /><div className="parameter-section"><span className="parameter-number">01</span><div><b>Decision model</b><small>Strategy profile and event threshold</small></div></div><label className="field-label">STRATEGY PROFILE<select value={config.profile} onChange={(event) => setConfig((current) => ({ ...current, profile: event.target.value }))}><option value="tfi">TFI</option><option value="quote_imbalance">Quote imbalance</option><option value="trade_flow_momentum">Trade flow momentum</option></select></label><div className="parameter-section"><span className="parameter-number">02</span><div><b>Execution timing</b><small>Delay between observed quote and arrival</small></div></div><label className="field-label">EXECUTION MODEL<select value={config.fillModel} onChange={(event) => setConfig((current) => ({ ...current, fillModel: event.target.value }))}><option value="top-of-book">Top of book taker IOC</option><option value="l2-depth">L2 depth</option></select></label><div className="two-fields"><label className="field-label">DELAY TIME (µs)<input type="number" min="0" step="1000" value={config.latencyUs} onChange={(event) => setConfig((current) => ({ ...current, latencyUs: Number(event.target.value) }))} /></label><label className="field-label">FEE (bps)<input type="number" min="0" step="0.1" value={config.feeBps} onChange={(event) => setConfig((current) => ({ ...current, feeBps: Number(event.target.value) }))} /></label></div><div className="two-fields"><label className="field-label">STARTING CASH<input type="number" value={config.startingCash} onChange={(event) => setConfig((current) => ({ ...current, startingCash: Number(event.target.value) }))} /></label><label className="field-label">MAX ORDERS<input type="number" value={12} readOnly /></label></div><div className="parameter-summary"><span><TimerReset size={14} /> delay_time <b>{config.latencyUs.toLocaleString()} µs</b></span><span><WalletCards size={14} /> fee <b>{config.feeBps.toFixed(2)} bps</b></span></div><PrimaryButton icon={<Zap size={15} />} onClick={onCreate} disabled={loading}>{loading ? "Runner active…" : "Run experiment"}</PrimaryButton></section>
      </div>
      <div className="setup-note panel"><Gauge size={17} /><div><strong>Execution realism must stay explicit</strong><p>L2 quality, latency, fees and fill semantics are part of the replay contract. Degraded depth data is shown as a warning rather than silently treated as queue-replay truth.</p></div></div>
    </div>
  );
}

function Workbench({ replay, snapshot, loading, onLibrary, onCommand, onSeek, onInspectFill }: { replay: ReplayStateV2; snapshot: Snapshot; loading: boolean; onLibrary: () => void; onCommand: (command: string) => void; onSeek: (value: number) => void; onInspectFill: (eventId: string) => void }) {
  const [tab, setTab] = useState<Tab>("Events");
  const [rawEventId, setRawEventId] = useState<string | null>(null);
  const [range, setRange] = useState("all");
  const window = useReplayWindow(replay, range);
  const fillAvailable = replay.chain.fill !== null;
  const story = {signal: !!replay.chain.signal, order: !!replay.chain.intent, arrival: !!replay.chain.arrival, fill: fillAvailable};
  function inspect(eventId: string, eventType: string) {
    setRawEventId(eventId);
    if (eventType === "fill_created" || eventType === "fill") onInspectFill(eventId);
  }

  return (
    <div className="workbench-stack">
      <section className="hero-summary panel"><div className="hero-identity"><div className="symbol-badge">{snapshot.symbol.slice(0, 2)}</div><div><h1>{snapshot.symbol}</h1><p>{snapshot.datasetDate} · {snapshot.strategy} · {snapshot.executionModel}</p><code>{snapshot.runId}</code></div></div><div className="hero-event"><span className="eyebrow">HISTORICAL CURSOR</span><strong>{fillAvailable ? `${snapshot.fill.side} ${snapshot.fill.qty} ${snapshot.symbol} @ ${snapshot.fill.price}` : snapshot.state}</strong><p>{fillAvailable ? `Fill ${snapshot.fill.fillId} · realized Δ ${snapshot.fill.realizedPnlDelta} · execution Δ ${snapshot.fill.netPnlDelta}` : "Replay the session or click a signal/order/fill marker to inspect that historical moment."}</p></div><div className="hero-mark"><span>MARK</span><strong>{snapshot.mid}</strong><small>{snapshot.replayState} · {snapshot.progress}%</small></div><GhostButton onClick={onLibrary}>Experiments</GhostButton></section>
      <ReplayToolbar speed={replay.speed} snapshot={snapshot} loading={loading} onCommand={onCommand} onSeek={onSeek} />
      <div className="metric-strip"><Metric label="MARK" value={snapshot.mid} tone="blue" /><Metric label="POSITION" value={snapshot.position.positionQty} tone="teal" /><Metric label="REALIZED PNL" value={snapshot.pnl.realizedPnl} tone="teal" /><Metric label="UNREALIZED PNL" value={snapshot.pnl.unrealizedPnl} tone="amber" /><Metric label="EQUITY" value={snapshot.pnl.netEquity} tone="blue" /></div>
      <div className="source-strip"><span className="source-label">MARKET STATE</span><strong>{snapshot.datasetDate} · {snapshot.symbol}</strong><span>bid {snapshot.bid} / ask {snapshot.ask}</span><span className="source-note">spread {snapshot.spread} · delay {snapshot.delayUs.toLocaleString()} µs · fee {snapshot.feeBps.toFixed(2)} bps</span><span className="cursor-readout">{snapshot.replayTime} · cursor {snapshot.eventCursor}</span></div>
      <div className="market-replay-grid"><PriceChart state={replay} window={window} range={range} onRange={setRange} onInspect={inspect} /><OrderBook snapshot={snapshot} /></div>
      <div className="historical-analysis-grid"><HistoricalTradeAnalysis state={replay} onInspect={inspect} /><EquityChart window={window} /></div>
      <div className="explain-grid"><StoryPanel title="HISTORICAL STRATEGY OPPORTUNITY" icon={<Target size={15} />} tone="amber"><strong>{snapshot.strategySignal.profile} · signal {snapshot.strategySignal.signal} / threshold {snapshot.strategySignal.threshold}</strong><p>{snapshot.strategySignal.reason || "Move to a strategy signal or order event to inspect the historical trigger."}</p><DataLine label="Observed quote" value={snapshot.strategySignal.observedQuote} /><DataLine label="Order side / qty" value={`${snapshot.orderIntent.side} ${snapshot.orderIntent.qty}`} /></StoryPanel><StoryPanel title="EXECUTION CONDITIONS" icon={<ArrowDownToLine size={15} />} tone="blue"><strong>{snapshot.orderArrival.arrivalQuote}</strong><p>Order {snapshot.orderArrival.orderId} · status {snapshot.orderArrival.orderStatus}</p><DataLine label="Actual latency" value={snapshot.orderArrival.actualLatencyUs} /><DataLine label="Latency slippage" value={snapshot.orderArrival.latencySlippageBps} /></StoryPanel><StoryPanel title="CURRENT ACCOUNT STATE" icon={<WalletCards size={15} />} tone="teal"><strong>Position {snapshot.position.positionQty} · equity {snapshot.position.equity}</strong><p>Realized {snapshot.pnl.realizedPnl} · unrealized {snapshot.pnl.unrealizedPnl}</p><DataLine label="Avg entry" value={snapshot.position.avgEntryPrice} /><DataLine label="Fees paid" value={snapshot.position.feesPaid} /></StoryPanel></div>
      <div className="analysis-grid"><TradeStory snapshot={snapshot} story={story} /><section className="attribution-panel panel"><PanelHeading icon={<WalletCards size={16} />} title="Selected fill attribution" subtitle="Runner-derived execution contribution at this historical cursor" /><div className="attribution-list"><DataLine label="Execution components" value={snapshot.fill.attribution || "—"} /><DataLine label="Realized PnL" value={snapshot.pnl.realizedPnl} /><DataLine label="Unrealized PnL" value={snapshot.pnl.unrealizedPnl} /><DataLine label="Selected fill Δ" value={snapshot.pnl.selectedFillDelta} /><DataLine label="Net equity" value={snapshot.pnl.netEquity} /></div></section></div>
      <section className="event-panel panel"><div className="event-toolbar"><div className="tabs">{tabs.map(item => <button key={item} className={tab === item ? "selected" : ""} onClick={() => setTab(item)}>{item}</button>)}</div></div>{tab === "Position" ? <pre className="event-tape">{snapshot.positionText}</pre> : tab === "PnL" ? <pre className="event-tape">{JSON.stringify(replay.account,null,2)}</pre> : <ReplayTable state={replay} kind={tab === "Signals" ? "strategy_signal" : tab === "Orders" ? "order_intent" : tab === "Fills" ? "fill_created" : null} onInspect={inspect} />}</section>
      <div className="inspector-grid"><section className="inspector panel"><div className="panel-kicker"><span>DECISION TRACE</span><b>/ event {replay.chain.fill?.eventId ?? replay.chain.intent?.eventId ?? "—"}</b></div><p>Missing stages: {replay.chain.missing.join(", ") || "none"}</p><pre>{snapshot.causal}</pre></section><RawInspector state={replay} eventId={rawEventId} /></div>
    </div>
  );
}

function ReplayToolbar({ speed, snapshot, loading, onCommand, onSeek }: { speed: number; snapshot: Snapshot; loading: boolean; onCommand: (command: string) => void; onSeek: (value: number) => void }) {
  return <section className="replay-toolbar panel"><button className="control primary-control" disabled={loading} onClick={() => onCommand("play")}><Play size={14} fill="currentColor" /> Play</button><button className="control" onClick={() => onCommand("pause")}><Pause size={14} /> Pause</button><button className="control" onClick={() => onCommand("stepBack")}><StepBack size={14} /> Step back</button><button className="control" onClick={() => onCommand("stepForward")}><StepForward size={14} /> Step</button><button className="control" onClick={() => onCommand("reset")}><RotateCcw size={14} /> Reset</button><span className="toolbar-divider" /><button className="control compact" onClick={() => onCommand("speedDown")}>Speed −</button><span className="speed-readout">{speed}×</span><button className="control compact" onClick={() => onCommand("speedUp")}>Speed +</button><div className="seek-control"><span>Seek</span><input type="range" min="0" max="1" step="0.001" value={snapshot.progress / 100} onChange={(event) => onSeek(Number(event.target.value))} /><span>{snapshot.progress.toFixed(1)}%</span></div><span className="toolbar-state"><span className="status-dot ready" />{snapshot.replayState}</span></section>;
}

function OrderBook({ snapshot }: { snapshot: Snapshot }) {
  return <section className="book-panel panel"><PanelHeading icon={<BookOpen size={16} />} title="Order book" subtitle="Current cursor snapshot" /><div className="book-head"><span>PRICE</span><span>QTY</span><span>CUM.</span></div><div className="book-levels asks">{snapshot.orderBook.asks.slice().reverse().map((level) => <BookRow key={`ask-${level.price}`} level={level} side="ask" />)}</div><div className="book-mid"><span>ASK</span><strong>{snapshot.orderBook.bestAsk}</strong><span>spread {snapshot.orderBook.spread}</span></div><div className="book-levels bids">{snapshot.orderBook.bids.map((level) => <BookRow key={`bid-${level.price}`} level={level} side="bid" />)}</div><div className="book-footer">{snapshot.orderBook.updateCount} updates · {snapshot.orderBook.snapshotBatchCount} snapshot batches · {snapshot.orderBook.quality}</div></section>;
}

function BookRow({ level, side }: { level: { price: string; qty: string; cumulativeQty: string }; side: "ask" | "bid" }) {
  return <div className="book-row"><span className={side === "ask" ? "ask-price" : "bid-price"}>{level.price}</span><span>{level.qty}</span><span>{level.cumulativeQty}</span></div>;
}

function TradeStory({ snapshot, story }: { snapshot: Snapshot; story: { signal: boolean; order: boolean; arrival: boolean; fill: boolean } }) {
  return <section className="trade-story panel"><PanelHeading icon={<ListTree size={16} />} title="Trade story" subtitle="The causal chain at this cursor" /><Stage n="01" label="SIGNAL" value={`${snapshot.strategySignal.signal} · ${snapshot.strategySignal.reason}`} active={story.signal} tone="amber" /><Stage n="02" label="ORDER" value={`${snapshot.orderIntent.side} ${snapshot.orderIntent.qty} · ${snapshot.orderIntent.intentId}`} active={story.order} tone="blue" /><Stage n="03" label="ARRIVAL" value={`${snapshot.orderArrival.actualLatencyUs} · ${snapshot.orderArrival.orderStatus}`} active={story.arrival} tone="violet" /><Stage n="04" label="FILL" value={story.fill ? `${snapshot.fill.price} · ${snapshot.fill.liquidity}` : "No fill at cursor"} active={story.fill} tone="teal" /><div className="story-foot">Each step is sourced from the Runner event chain.</div></section>;
}

function Stage({ n, label, value, active, tone }: { n: string; label: string; value: string; active: boolean; tone: string }) { return <div className={`stage ${active ? "active" : ""} ${tone}`}><span className="stage-number">{n}</span><span className="stage-label">{label}</span><strong>{value}</strong></div>; }

function StoryPanel({ title, icon, tone, children }: { title: string; icon: React.ReactNode; tone: string; children: React.ReactNode }) { return <section className={`story-panel panel ${tone}`}><div className="story-title">{icon}<strong>{title}</strong></div><div className="story-body">{children}</div></section>; }
function DataLine({ label, value }: { label: string; value: string }) { return <div className="data-line"><span>{label}</span><code>{value || "—"}</code></div>; }
function PanelHeading({ icon, title, subtitle }: { icon: React.ReactNode; title: string; subtitle: string }) { return <div className="panel-heading"><div className="heading-icon">{icon}</div><div><h2>{title}</h2><p>{subtitle}</p></div></div>; }
function Metric({ label, value, tone }: { label: string; value: string; tone: string }) { return <div className="metric"><span>{label}</span><strong className={tone}>{value}</strong></div>; }
function Status({ status }: { status: string }) { return <span className={`status ${status.toLowerCase()}`}><i />{status}</span>; }
function PrimaryButton({ icon, children, onClick, disabled }: { icon?: React.ReactNode; children: React.ReactNode; onClick: () => void; disabled?: boolean }) { return <button className="button primary-button" onClick={onClick} disabled={disabled}>{icon}{children}</button>; }
function GhostButton({ children, onClick }: { children: React.ReactNode; onClick: () => void }) { return <button className="button ghost-button" onClick={onClick}>{children}</button>; }
function CopyButton({ value }: { value: string }) { return <button className="copy-button" onClick={() => void navigator.clipboard?.writeText(value)}>Copy raw JSON</button>; }
function EmptyWorkbench({ onLibrary }: { onLibrary: () => void }) { return <div className="empty-workbench panel"><CirclePlay size={28} /><h1>Open a historical run to begin</h1><p>Choose an experiment to replay the market, review strategy orders and fills, and study how the account PnL evolved.</p><GhostButton onClick={onLibrary}>Open Experiments</GhostButton></div>; }
