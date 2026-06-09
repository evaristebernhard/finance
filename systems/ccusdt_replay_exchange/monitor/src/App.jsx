import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Clock3,
  FileSearch,
  Link2,
  Radio,
  RefreshCw,
  ShieldCheck,
  Wifi,
  XCircle,
} from "lucide-react";
import React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const DEFAULT_RUN = "det_barrier_full_span60s_20260521";

function fmt(value, digits = 4) {
  if (value === null || value === undefined || value === "") return "--";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "--";
    if (Math.abs(value) >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
    return value.toLocaleString(undefined, { maximumFractionDigits: digits });
  }
  return String(value);
}

function fmtBps(value) {
  if (value === null || value === undefined) return "--";
  return `${fmt(value, 4)} bps`;
}

function fmtTsUs(value) {
  if (!value) return "--";
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return `${Math.trunc(n / 1_000_000)}s + ${Math.trunc(n % 1_000_000)}us`;
}

function statusClass(status) {
  if (status === "filled") return "good";
  if (status === "rejected" || status === "skipped") return "bad";
  if (status === "arrived" || status === "ack" || status === "scheduled") return "warn";
  return "muted";
}

function firstNonNull(...values) {
  return values.find((value) => value !== null && value !== undefined);
}

function profileLine(summary) {
  const parts = [
    summary?.transport_profile,
    summary?.fill_profile,
    summary?.policy_profile,
    summary?.capacity_profile,
    summary?.exit_profile,
  ].filter(Boolean);
  return parts.length ? parts.join(" / ") : "profile manifest unavailable";
}

function StatTile({ label, value, sub, tone = "neutral", icon }) {
  return (
    <section className={`stat-tile ${tone}`}>
      <div className="stat-head">
        {icon}
        <span>{label}</span>
      </div>
      <strong>{value}</strong>
      {sub ? <small>{sub}</small> : null}
    </section>
  );
}

function WarningList({ warnings = [] }) {
  if (!warnings.length) {
    return (
      <div className="ok-line">
        <CheckCircle2 size={16} />
        <span>run artifacts look internally consistent</span>
      </div>
    );
  }
  return (
    <div className="warning-list">
      {warnings.map((warning, index) => (
        <div className={`warning ${warning.level ?? "warn"}`} key={`${warning.message}-${index}`}>
          <AlertTriangle size={15} />
          <span>{warning.message}</span>
        </div>
      ))}
    </div>
  );
}

function RunSelector({ runs, selectedRun, onSelect, onRefresh }) {
  return (
    <section className="side-section">
      <div className="section-title">
        <FileSearch size={16} />
        <span>Offline runs</span>
        <button className="icon-button" type="button" onClick={onRefresh} title="Refresh run list">
          <RefreshCw size={15} />
        </button>
      </div>
      <div className="run-list">
        {runs.map((run) => (
          <button
            className={`run-item ${selectedRun === run.run_dir ? "active" : ""}`}
            key={run.run_dir}
            type="button"
            onClick={() => onSelect(run.run_dir)}
            title={run.run_dir}
          >
            <span className="run-name">{run.run_id}</span>
            <span className="run-meta">
              {run.transport_profile ?? "unknown transport"} · {fmt(run.orders_submitted, 0)}/{fmt(run.fills_created, 0)}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function LivePanel({ liveConfig, setLiveConfig, liveStats, liveConnected, onConnect, onDisconnect }) {
  return (
    <section className="side-section">
      <div className="section-title">
        <Wifi size={16} />
        <span>Live read-only</span>
      </div>
      <label>
        Public stream
        <input
          value={liveConfig.publicAddr}
          onChange={(event) => setLiveConfig({ ...liveConfig, publicAddr: event.target.value })}
        />
      </label>
      <label>
        Private stream
        <input
          value={liveConfig.privateAddr}
          onChange={(event) => setLiveConfig({ ...liveConfig, privateAddr: event.target.value })}
        />
      </label>
      <label>
        State URL
        <input
          value={liveConfig.stateUrl}
          onChange={(event) => setLiveConfig({ ...liveConfig, stateUrl: event.target.value })}
        />
      </label>
      <div className="button-row">
        <button className="primary-button" type="button" onClick={onConnect} disabled={liveConnected}>
          <Radio size={16} />
          Connect
        </button>
        <button className="ghost-button" type="button" onClick={onDisconnect} disabled={!liveConnected}>
          <XCircle size={16} />
          Stop
        </button>
      </div>
      <div className="live-mini">
        <span>public {fmt(liveStats?.public_events, 0)}</span>
        <span>private {fmt(liveStats?.private_events, 0)}</span>
        <span>fills {fmt(liveStats?.fills, 0)}</span>
        <span>mid {fmt(liveStats?.last_mid, 6)}</span>
      </div>
    </section>
  );
}

function SummaryHeader({ payload, liveStats }) {
  const summary = payload?.summary;
  const account = summary?.final_account ?? liveStats?.account;
  const orders = firstNonNull(summary?.orders_submitted, liveStats?.order_acks, 0);
  const fills = firstNonNull(summary?.fills_created, liveStats?.fills, 0);
  const lag = firstNonNull(summary?.arrival_quote_lag_count, 0);
  const bridgeErrors = firstNonNull(summary?.bridge_errors, liveStats?.errors?.length, 0);
  return (
    <header className="app-header">
      <div>
        <p className="eyebrow">CCUSDT Replay Exchange</p>
        <h1>{summary?.run_id ?? liveStats?.run_id ?? "Monitor"}</h1>
        <p className="profile-line">{summary ? profileLine(summary) : "live public/private streams, read-only"}</p>
      </div>
      <div className="stat-grid">
        <StatTile
          label="Orders / fills"
          value={`${fmt(orders, 0)} / ${fmt(fills, 0)}`}
          sub={summary?.source_label ?? "live stream"}
          icon={<Activity size={16} />}
          tone={orders === fills ? "good" : "warn"}
        />
        <StatTile
          label="Final equity"
          value={fmt(account?.equity, 6)}
          sub={`realized ${fmt(account?.realized_pnl, 8)}`}
          icon={<BarChart3 size={16} />}
        />
        <StatTile
          label="Arrival lag"
          value={fmt(lag, 0)}
          sub="arrival_quote_lag_count"
          icon={<Clock3 size={16} />}
          tone={lag === 0 ? "good" : "warn"}
        />
        <StatTile
          label="Bridge errors"
          value={fmt(bridgeErrors, 0)}
          sub={summary?.determinism_mode ?? "live diagnostics"}
          icon={<ShieldCheck size={16} />}
          tone={bridgeErrors === 0 ? "good" : "bad"}
        />
      </div>
    </header>
  );
}

function ChainTable({ chains, selectedIntentId, onSelect }) {
  return (
    <section className="main-panel">
      <div className="panel-header">
        <div>
          <h2>订单因果链</h2>
          <p>每一行是一条 intent_id 聚合链，顺序追踪 capacity、arrival、ack、fill 和 portfolio。</p>
        </div>
        <span className="badge">{chains.length} chains</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>intent</th>
              <th>status</th>
              <th>side</th>
              <th>cell</th>
              <th>capacity</th>
              <th>requested</th>
              <th>actual</th>
              <th>obs seq</th>
              <th>arr seq</th>
              <th>fill</th>
              <th>spread</th>
              <th>lat slippage</th>
            </tr>
          </thead>
          <tbody>
            {chains.map((chain) => (
              <tr
                className={selectedIntentId === chain.intent_id ? "selected" : ""}
                key={chain.intent_id}
                onClick={() => onSelect(chain.intent_id)}
              >
                <td className="mono strong">{chain.intent_id}</td>
                <td>
                  <span className={`pill ${statusClass(chain.status)}`}>{chain.status}</span>
                </td>
                <td>{chain.side ?? "--"}</td>
                <td>{chain.cell ?? "--"}</td>
                <td>{chain.capacity_source ?? "--"}</td>
                <td>{fmt(chain.requested_exposure, 4)}</td>
                <td>{fmt(chain.actual_exposure, 4)}</td>
                <td>{fmt(chain.observed_seq, 0)}</td>
                <td>{fmt(chain.arrival_seq, 0)}</td>
                <td>{fmt(chain.fill_price, 6)}</td>
                <td>{fmtBps(chain.spread_bps_at_arrival)}</td>
                <td>{fmtBps(chain.latency_slippage_bps)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function QuoteCompare({ chain }) {
  const rows = [
    ["bid", chain?.observed_quote?.bid, chain?.arrival_quote?.bid],
    ["ask", chain?.observed_quote?.ask, chain?.arrival_quote?.ask],
    ["mid", chain?.observed_quote?.mid, chain?.arrival_quote?.mid],
    ["quote seq", chain?.observed_quote?.seq, chain?.arrival_quote?.seq],
  ];
  return (
    <div className="quote-grid">
      <div className="quote-head">field</div>
      <div className="quote-head">observed</div>
      <div className="quote-head">arrival</div>
      {rows.flatMap(([label, observed, arrival]) => [
        <div key={`${label}-l`}>{label}</div>,
        <div className="mono" key={`${label}-o`}>{fmt(observed, 6)}</div>,
        <div className="mono" key={`${label}-a`}>{fmt(arrival, 6)}</div>,
      ])}
    </div>
  );
}

function ChainDetail({ chain }) {
  if (!chain) {
    return (
      <aside className="detail-panel empty">
        <Link2 size={22} />
        <p>选择一条订单链，查看 observed quote、arrival quote、capacity 和成交详情。</p>
      </aside>
    );
  }
  const ordered = ["capacity_decision", "order_scheduled", "order_arrived", "order_ack", "order_reject", "fill", "portfolio_state_on_change"];
  const eventSet = new Set(chain.events);
  return (
    <aside className="detail-panel">
      <div className="panel-header tight">
        <div>
          <h2>Intent {chain.intent_id}</h2>
          <p>{chain.client_order_id ?? "client order id unavailable"}</p>
        </div>
        <span className={`pill ${statusClass(chain.status)}`}>{chain.status}</span>
      </div>
      <section className="detail-section">
        <h3>Causal chain</h3>
        <div className="timeline">
          {ordered.map((eventType) => (
            <div className={`timeline-row ${eventSet.has(eventType) ? "seen" : ""}`} key={eventType}>
              <span className="dot" />
              <span>{eventType}</span>
            </div>
          ))}
        </div>
      </section>
      <section className="detail-section">
        <h3>Capacity</h3>
        <dl className="kv">
          <dt>cell</dt>
          <dd>{chain.cell ?? "--"}</dd>
          <dt>source</dt>
          <dd>{chain.capacity_source ?? "--"}</dd>
          <dt>requested</dt>
          <dd>{fmt(chain.requested_exposure, 4)}</dd>
          <dt>actual</dt>
          <dd>{fmt(chain.actual_exposure, 4)}</dd>
          <dt>clipped</dt>
          <dd>{fmt(chain.clipped_exposure, 4)}</dd>
          <dt>position</dt>
          <dd>{chain.shadow_position_id ?? "--"}</dd>
        </dl>
      </section>
      <section className="detail-section">
        <h3>Quote at decision and fill</h3>
        <QuoteCompare chain={chain} />
      </section>
      <section className="detail-section">
        <h3>Execution</h3>
        <dl className="kv">
          <dt>observed ts</dt>
          <dd>{fmtTsUs(chain.observed_local_ts_us)}</dd>
          <dt>arrival ts</dt>
          <dd>{fmtTsUs(chain.arrival_local_ts_us)}</dd>
          <dt>fill price</dt>
          <dd>{fmt(chain.fill_price, 6)}</dd>
          <dt>fill qty</dt>
          <dd>{fmt(chain.fill_qty, 6)}</dd>
          <dt>spread</dt>
          <dd>{fmtBps(chain.spread_bps_at_arrival)}</dd>
          <dt>latency slip</dt>
          <dd>{fmtBps(chain.latency_slippage_bps)}</dd>
        </dl>
      </section>
    </aside>
  );
}

function EventChart({ eventTypeCounts }) {
  const data = useMemo(() => {
    return Object.entries(eventTypeCounts ?? {})
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 12);
  }, [eventTypeCounts]);
  return (
    <section className="bottom-panel">
      <div className="panel-header tight">
        <div>
          <h2>Event types</h2>
          <p>compact log 类型分布。</p>
        </div>
      </div>
      <div className="chart-box">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data} layout="vertical" margin={{ top: 6, right: 20, bottom: 6, left: 120 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2c302d" />
            <XAxis type="number" stroke="#8f978f" />
            <YAxis type="category" dataKey="name" stroke="#8f978f" width={132} />
            <Tooltip contentStyle={{ background: "#191b19", border: "1px solid #393d36", color: "#e9ece6" }} />
            <Bar dataKey="value" fill="#76d6b0" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function TimingPanel({ timing }) {
  const rows = [
    ["events/s", timing?.events_per_sec ?? timing?.events_per_second],
    ["market read ms", timing?.market_read_ms],
    ["bridge write ms", timing?.bridge_stdin_write_ms],
    ["bridge wait ms", timing?.bridge_wait_time_ms ?? timing?.bridge_stdout_drain_and_response_ms],
    ["fill ms", timing?.runner_fill_time_ms ?? timing?.order_submit_fill_ms],
    ["batches", timing?.batch_count ?? timing?.public_batches_sent],
    ["barriers", timing?.barrier_count ?? timing?.public_barriers_triggered],
    ["requeued suffix", timing?.requeued_suffix_count ?? timing?.public_requeued_suffix_count],
  ];
  return (
    <section className="bottom-panel">
      <div className="panel-header tight">
        <div>
          <h2>Timing breakdown</h2>
          <p>定位 strict 热路径慢点。</p>
        </div>
      </div>
      <div className="timing-grid">
        {rows.map(([label, value]) => (
          <div className="timing-row" key={label}>
            <span>{label}</span>
            <strong>{fmt(value, 3)}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function ProfilePanel({ profile }) {
  const rows = [
    ["transport", profile?.transport_profile?.name],
    ["fill", profile?.fill_profile?.name],
    ["latency", profile?.latency_profile?.name],
    ["capacity", profile?.capacity_profile?.name],
    ["policy", profile?.policy_profile?.name],
    ["exit", profile?.exit_profile?.name],
    ["hash", profile?.profile_manifest_hash],
  ];
  return (
    <section className="bottom-panel">
      <div className="panel-header tight">
        <div>
          <h2>Profile manifest</h2>
          <p>避免混比不同实验口径。</p>
        </div>
      </div>
      <dl className="kv profile-kv">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value ?? "--"}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export default function App() {
  const [mode, setMode] = useState("offline");
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedIntentId, setSelectedIntentId] = useState(null);
  const [liveConfig, setLiveConfig] = useState({
    publicAddr: "127.0.0.1:8801",
    privateAddr: "127.0.0.1:8802",
    stateUrl: "http://127.0.0.1:8804/api/state",
  });
  const [liveStats, setLiveStats] = useState(null);
  const liveRef = useRef(null);

  async function loadRuns() {
    const response = await fetch("/api/runs");
    if (!response.ok) throw new Error(`run list failed: ${response.status}`);
    const value = await response.json();
    setRuns(value.runs ?? []);
    if (!selectedRun && value.runs?.length) {
      const preferred = value.runs.find((run) => run.run_dir.includes(DEFAULT_RUN)) ?? value.runs[0];
      setSelectedRun(preferred.run_dir);
    }
  }

  async function loadRun(runDir) {
    if (!runDir) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`/api/offline-run?runDir=${encodeURIComponent(runDir)}`);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text);
      }
      const value = await response.json();
      setPayload(value);
      const firstFilled = value.chains?.find((chain) => chain.status === "filled") ?? value.chains?.[0] ?? null;
      setSelectedIntentId(firstFilled?.intent_id ?? null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRuns().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (mode === "offline" && selectedRun) {
      loadRun(selectedRun);
    }
  }, [selectedRun, mode]);

  function connectLive() {
    if (liveRef.current) liveRef.current.close();
    setMode("live");
    setLiveStats(null);
    const params = new URLSearchParams(liveConfig);
    const source = new EventSource(`/api/live-stream?${params.toString()}`);
    liveRef.current = source;
    source.addEventListener("snapshot", (event) => {
      const value = JSON.parse(event.data);
      setLiveStats(value.stats);
    });
    source.addEventListener("error", () => {
      setLiveStats((current) => ({ ...(current ?? {}), connected: false }));
    });
  }

  function disconnectLive() {
    if (liveRef.current) liveRef.current.close();
    liveRef.current = null;
    setLiveStats((current) => ({ ...(current ?? {}), connected: false }));
  }

  useEffect(() => () => disconnectLive(), []);

  const chains = payload?.chains ?? [];
  const selectedChain = chains.find((chain) => chain.intent_id === selectedIntentId) ?? chains[0] ?? null;

  return (
    <div className="app-shell">
      <SummaryHeader payload={mode === "offline" ? payload : null} liveStats={mode === "live" ? liveStats : null} />
      <main className="layout">
        <aside className="sidebar">
          <div className="mode-tabs" role="tablist" aria-label="Monitor mode">
            <button className={mode === "offline" ? "active" : ""} type="button" onClick={() => setMode("offline")}>
              <FileSearch size={16} />
              Offline
            </button>
            <button className={mode === "live" ? "active" : ""} type="button" onClick={() => setMode("live")}>
              <Radio size={16} />
              Live
            </button>
          </div>
          {mode === "offline" ? (
            <RunSelector runs={runs} selectedRun={selectedRun} onSelect={setSelectedRun} onRefresh={loadRuns} />
          ) : (
            <LivePanel
              liveConfig={liveConfig}
              setLiveConfig={setLiveConfig}
              liveStats={liveStats}
              liveConnected={Boolean(liveRef.current)}
              onConnect={connectLive}
              onDisconnect={disconnectLive}
            />
          )}
          <section className="side-section">
            <div className="section-title">
              <AlertTriangle size={16} />
              <span>Run warnings</span>
            </div>
            <WarningList warnings={payload?.warnings ?? []} />
          </section>
        </aside>
        <section className="workspace">
          {error ? <div className="error-banner">{error}</div> : null}
          {loading ? <div className="loading">Loading run artifacts...</div> : null}
          {mode === "offline" ? (
            <div className="split-view">
              <ChainTable chains={chains} selectedIntentId={selectedIntentId} onSelect={setSelectedIntentId} />
              <ChainDetail chain={selectedChain} />
            </div>
          ) : (
            <section className="main-panel live-panel">
              <div className="panel-header">
                <div>
                  <h2>Live stream snapshot</h2>
                  <p>只读 public/private/state；没有 order ingress。</p>
                </div>
                <span className={`pill ${liveStats?.connected === false ? "bad" : "good"}`}>
                  {liveStats?.connected === false ? "disconnected" : "read-only"}
                </span>
              </div>
              <div className="live-grid">
                {Object.entries(liveStats ?? {}).map(([key, value]) => {
                  if (typeof value === "object" && value !== null) return null;
                  return (
                    <div className="timing-row" key={key}>
                      <span>{key}</span>
                      <strong>{fmt(value, 4)}</strong>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
          {mode === "offline" ? (
            <div className="bottom-grid">
              <EventChart eventTypeCounts={payload?.eventTypeCounts} />
              <TimingPanel timing={payload?.summary?.timing_ms} />
              <ProfilePanel profile={payload?.profile_manifest} />
            </div>
          ) : null}
        </section>
      </main>
    </div>
  );
}
